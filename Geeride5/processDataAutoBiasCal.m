function out = processDataAutoBiasCal(path, calpath, cfg)

%% =========================
% 1) LOAD MEASUREMENT DATA
% ==========================
[t_acc, ~, ~, gyro_all, acc_all, mag_all] = CSV_Import_lowpass(cfg.RawplotsOn, path);

t_all = t_acc;

idx_meas = (t_all >= cfg.windows.measStart) & (t_all <= cfg.windows.measStop);

t    = t_all(idx_meas);
gyro = gyro_all(idx_meas, :);
acc  = acc_all(idx_meas,  :);
mag  = mag_all(idx_meas,  :);

if isempty(t)
    error('V measurement data neboli najdene ziadne vzorky v measStart/measStop.');
end

%% =========================
% 2) LOAD CALIBRATION DATA
% ==========================
useExternalCal = false;

if nargin >= 2 && ~isempty(calpath) && (isfolder(calpath) || isfile(calpath))
    try
        [t_cal_file, ~, ~, gyro_cal_all, acc_cal_all, mag_cal_all] = CSV_Import_lowpass(cfg.RawplotsOn, calpath);
        useExternalCal = true;
    catch ME
        warning('Nepodarilo sa nacitat calibration data z calpath: %s\nPouzijem measurement data ako fallback.\nDovod: %s', ...
            string(calpath), ME.message);

        t_cal_file   = t_acc;
        gyro_cal_all = gyro_all;
        acc_cal_all  = acc_all;
        mag_cal_all  = mag_all;
    end
else
    warning('Calibration path neexistuje alebo nebol zadany. Pouzijem measurement data ako fallback.');
    t_cal_file   = t_acc;
    gyro_cal_all = gyro_all;
    acc_cal_all  = acc_all;
    mag_cal_all  = mag_all;
end

%% =========================
% 3) CALIBRATION WINDOWS
% ==========================
idx_gyro_cal = (t_cal_file >= cfg.windows.gyroCalStart) & (t_cal_file <= cfg.windows.gyroCalStop);
idx_mag_cal  = (t_cal_file >= cfg.windows.magCalStart)  & (t_cal_file <= cfg.windows.magCalStop);

t_gyro_cal = t_cal_file(idx_gyro_cal);
gyro_cal   = gyro_cal_all(idx_gyro_cal, :);
acc_cal    = acc_cal_all(idx_gyro_cal,  :); %#ok<NASGU>

t_mag_cal  = t_cal_file(idx_mag_cal);
mag_cal    = mag_cal_all(idx_mag_cal, :);

if isempty(gyro_cal)
    error('Gyro calibration window je prazdny. Skontroluj gyroCalStart/gyroCalStop.');
end

if isempty(mag_cal)
    error('Mag calibration window je prazdny. Skontroluj magCalStart/magCalStop.');
end

%% =========================
% 4) INITIAL GYRO BIAS
% ==========================
ConstantBias = estimateGyroBias(t_gyro_cal, gyro_cal, cfg.biasSeconds);
gyro = gyro - ConstantBias;

%% =========================
% 5) MAGNETOMETER CALIBRATION
% ==========================
[A, b, ~] = magcal(mag_cal);
mag = (mag - b) * A;

%% =========================
% 6) ACC GATING
% ==========================
accNormRaw = vecnorm(acc, 2, 2);
gRef = median(accNormRaw(1:min(100, numel(accNormRaw))));
accErr = abs(accNormRaw - gRef);
wAcc = accErr < cfg.accThreshold;

%% =========================
% 7) MAG GATING
% ==========================
magNorm = vecnorm(mag, 2, 2);
magRef = median(magNorm(1:min(200, numel(magNorm))));

if cfg.magTolerance <= 0
    wMag = true(size(magNorm));
else
    wMag = abs(magNorm - magRef) < cfg.magTolerance * magRef;
end

%% =========================
% 8) STILL DETECTION
% ==========================
gyroNorm = vecnorm(gyro, 2, 2);
accNorm  = vecnorm(acc,  2, 2);

stillMask = (gyroNorm < cfg.stillGyroThresh) & ...
            (abs(accNorm - gRef) < cfg.stillAccThresh);

%% =========================
% 9) DYNAMIC GYRO BIAS
% ==========================
dt = median(diff(t));
Fs = 1 / dt;

biasWin = max(3, round(cfg.stillBiasWindowSec * Fs));

gyroCorr = gyro;

for i = 1:length(t)
    if stillMask(i)
        i1 = max(1, i - floor(biasWin/2));
        i2 = min(length(t), i + floor(biasWin/2));

        idxStillLocal = stillMask(i1:i2);

        if sum(idxStillLocal) >= 5
            localGyro = gyro(i1:i2, :);
            localBias = mean(localGyro(idxStillLocal, :), 1, 'omitnan');
            gyroCorr(i, :) = gyro(i, :) - localBias;
        end
    end
end

%% =========================
% 10) MAHONY FILTER
% ==========================
Nfast = round(cfg.startupTime / dt);
Nfast = max(1, Nfast);

MahonyFilter = MahonyAHRS( ...
    'SamplePeriod', dt, ...
    'Kp', cfg.fast.Kp, ...
    'Ki', cfg.fast.Ki, ...
    'MagWeight', cfg.fast.MagWeight, ...
    'AccWeight', cfg.fast.AccWeight);

q = zeros(length(t), 4);

for i = 1:length(t)

    if i == Nfast + 1
        MahonyFilter.Kp        = cfg.run.Kp;
        MahonyFilter.Ki        = cfg.run.Ki;
        MahonyFilter.MagWeight = cfg.run.MagWeight;
        MahonyFilter.AccWeight = cfg.run.AccWeight;
    end

    if i <= Nfast
        baseKp        = cfg.fast.Kp;
        baseKi        = cfg.fast.Ki;
        baseMagWeight = cfg.fast.MagWeight;
        baseAccWeight = cfg.fast.AccWeight;
    else
        baseKp        = cfg.run.Kp;
        baseKi        = cfg.run.Ki;
        baseMagWeight = cfg.run.MagWeight;
        baseAccWeight = cfg.run.AccWeight;
    end

    MahonyFilter.Kp        = baseKp * double(wAcc(i));
    MahonyFilter.Ki        = baseKi;
    MahonyFilter.MagWeight = baseMagWeight * double(wMag(i));
    MahonyFilter.AccWeight = baseAccWeight * double(wAcc(i));

    MahonyFilter.Update(gyroCorr(i,:), acc(i,:), mag(i,:));
    q(i,:) = MahonyFilter.Quaternion;
end

%% =========================
% 11) QUATERNION -> EULER
% ==========================
qEstimated = quaternion(q);

eulerEstimated = eulerd(qEstimated, 'ZYX', 'frame');   % [yaw pitch roll]
eulerEstimated = [ ...
    eulerEstimated(:,3), ...
    eulerEstimated(:,2), ...
    eulerEstimated(:,1)  ...
]; % [roll pitch yaw]

eulerEstimated = rad2deg(unwrap(deg2rad(eulerEstimated)));

%% =========================
% 12) EULER LOWPASS
% ==========================
[b_eulerLP, a_eulerLP] = butter(cfg.Nbutter, cfg.eulerLPHz/(Fs/2), 'low');
eulerEstimated = filtfilt(b_eulerLP, a_eulerLP, eulerEstimated);

%% =========================
% 13) OUTPUT
% ==========================
out.t         = t;
out.euler     = eulerEstimated;
out.q         = qEstimated;

out.acc       = acc;
out.gyro      = gyroCorr;
out.mag       = mag;

out.wAcc      = wAcc;
out.wMag      = wMag;
out.stillMask = stillMask;

out.ConstantBias   = ConstantBias;
out.magCal_A       = A;
out.magCal_b       = b;
out.gRef           = gRef;
out.usedExternalCal = useExternalCal;
out.calpath        = calpath;

end
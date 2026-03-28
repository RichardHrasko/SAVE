function out = processDataAutoBias(path, cfg)

% Import
[t_acc, ~, ~, gyro_all, acc_all, mag_all] = CSV_Import_lowpass(cfg.RawplotsOn, path);

%% Time windows
t_all = t_acc;

idx_meas     = (t_all >= cfg.windows.measStart)    & (t_all <= cfg.windows.measStop);
idx_gyro_cal = (t_all >= cfg.windows.gyroCalStart) & (t_all <= cfg.windows.gyroCalStop);
idx_mag_cal  = (t_all >= cfg.windows.magCalStart)  & (t_all <= cfg.windows.magCalStop);

t = t_all(idx_meas);

gyro = gyro_all(idx_meas,:);
acc  = acc_all(idx_meas,:);
mag  = mag_all(idx_meas,:);

t_gyro_cal = t_all(idx_gyro_cal);
gyro_cal   = gyro_all(idx_gyro_cal,:);
acc_cal    = acc_all(idx_gyro_cal,:);

t_mag_cal = t_all(idx_mag_cal);
mag_cal   = mag_all(idx_mag_cal,:);

%% Initial gyroscope bias removal
ConstantBias = estimateGyroBias(t_gyro_cal, gyro_cal, cfg.biasSeconds);
gyro = gyro - ConstantBias;

%% Magnetometer calibration
[A,b,~] = magcal(mag_cal);
mag = (mag - b) * A;

%% Accelerometer gating
accNormRaw = vecnorm(acc,2,2);
gRef = median(accNormRaw(1:min(100,end)));
accErr = abs(accNormRaw - gRef);
wAcc = accErr < cfg.accThreshold;

%% Magnetometer gating
magNorm = vecnorm(mag,2,2);
magRef  = median(magNorm(1:min(200,end)));
wMag = abs(magNorm - magRef) < cfg.magTolerance * magRef;

%% Still detection
gyroNorm = vecnorm(gyro,2,2);
accNorm  = vecnorm(acc,2,2);

stillMask = (gyroNorm < cfg.stillGyroThresh) & ...
            (abs(accNorm - gRef) < cfg.stillAccThresh);

%% Dynamic gyro bias during still periods
dt = median(diff(t));
Fs = 1/dt;
biasWin = max(3, round(cfg.stillBiasWindowSec * Fs));

gyroCorr = gyro;

for i = 1:length(t)
    if stillMask(i)
        i1 = max(1, i - floor(biasWin/2));
        i2 = min(length(t), i + floor(biasWin/2));

        idxWin = stillMask(i1:i2);

        if sum(idxWin) >= 5
            localBias = mean(gyro(i1:i2,:), 1, 'omitnan');
            gyroCorr(i,:) = gyro(i,:) - localBias;
        end
    end
end

%% Mahony filter
Nfast = round(cfg.startupTime / dt);

MahonyFilter = MahonyAHRS( ...
    'SamplePeriod', dt, ...
    'Kp', cfg.fast.Kp, ...
    'Ki', cfg.fast.Ki, ...
    'MagWeight', cfg.fast.MagWeight, ...
    'AccWeight', cfg.fast.AccWeight);

q = zeros(length(t), 4);

for i = 1:length(t)

    if i == Nfast
        MahonyFilter.Kp        = cfg.run.Kp;
        MahonyFilter.Ki        = cfg.run.Ki;
        MahonyFilter.MagWeight = cfg.run.MagWeight;
        MahonyFilter.AccWeight = cfg.run.AccWeight;
    end

    % Gating
    MahonyFilter.Kp = cfg.run.Kp * wAcc(i);

    % ak budeš chcieť neskôr:
    % MahonyFilter.MagWeight = cfg.run.MagWeight * wMag(i);
    % MahonyFilter.AccWeight = cfg.run.AccWeight * wAcc(i);

    MahonyFilter.Update(gyroCorr(i,:), acc(i,:), mag(i,:));
    q(i,:) = MahonyFilter.Quaternion;
end

%% Quaternion -> Euler
qEstimated = quaternion(q);

eulerEstimated = eulerd(qEstimated, 'ZYX', 'frame');   % [yaw pitch roll]
eulerEstimated = [eulerEstimated(:,3) eulerEstimated(:,2) eulerEstimated(:,1)]; % [roll pitch yaw]

eulerEstimated = rad2deg(unwrap(deg2rad(eulerEstimated)));

%% Euler low-pass
[b_eulerLP, a_eulerLP] = butter(cfg.Nbutter, cfg.eulerLPHz/(Fs/2), 'low');
eulerEstimated = filtfilt(b_eulerLP, a_eulerLP, eulerEstimated);

%% Output
out.t         = t;
out.euler     = eulerEstimated;
out.q         = qEstimated;

out.acc       = acc;
out.gyro      = gyroCorr;
out.mag       = mag;

out.wAcc      = wAcc;
out.wMag      = wMag;
out.stillMask = stillMask;

end
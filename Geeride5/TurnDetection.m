function out = TurnDetection(t, euler, gyro, speed, cfg, doPlot)

    if nargin < 5 || isempty(cfg)
        cfg = struct;
    end
    if nargin < 6
        doPlot = false;
    end

    cfg = fillDefaults(cfg);

    t = t(:);
    speed = speed(:);

    roll = euler(:,1);
    yaw  = euler(:,3);

    roll = roll(:);
    yaw  = yaw(:);

    gyroX = gyro(:,1);
    gyroY = gyro(:,2);
    gyroZ = gyro(:,3);

    if numel(t) ~= numel(roll) || numel(speed) ~= numel(t) || size(gyro,1) ~= numel(t)
        error('t, euler, gyro, speed must have matching lengths');
    end

    dt = median(diff(t));
    Fs = 1/dt;

    yawUnwrap = rad2deg(unwrap(deg2rad(yaw)));
    yawRate = gradient(yawUnwrap, t);
    gyroNorm = sqrt(gyroX.^2 + gyroY.^2 + gyroZ.^2);

    nRoll  = max(1, round(cfg.rollSmoothSec * Fs));
    nYaw   = max(1, round(cfg.yawRateSmoothSec * Fs));
    nGyro  = max(1, round(cfg.gyroSmoothSec * Fs));
    nSpeed = max(1, round(cfg.speedSmoothSec * Fs));

    rollSm     = smoothdata(roll,     'movmean', nRoll);
    yawRateSm  = smoothdata(yawRate,  'movmean', nYaw);
    gyroNormSm = smoothdata(gyroNorm, 'movmean', nGyro);
    speedSm    = smoothdata(speed,    'movmean', nSpeed);

    absRoll    = abs(rollSm);
    absYawRate = abs(yawRateSm);

    condRoll  = absRoll >= cfg.rollThresh;
    condYaw   = absYawRate >= cfg.yawRateThresh;
    condGyro  = gyroNormSm >= cfg.gyroNormThresh;
    condSpeed = speedSm >= cfg.speedThresh;

    voteCount = double(condRoll) + double(condYaw) + double(condGyro) + double(condSpeed);
    mask = voteCount >= cfg.minVotes;

    if cfg.requireRoll
        mask = mask & condRoll;
    end

    if cfg.requireSpeed
        mask = mask & condSpeed;
    end

    minRegionSamples = max(1, round(cfg.minRegionSec * Fs));
    mask = removeShortTrueRegions(mask, minRegionSamples);

    d = diff([false; mask; false]);
    startIdx = find(d == 1);
    endIdx   = find(d == -1) - 1;

    candIdx = [];
    candVal = [];

    for i = 1:numel(startIdx)
        seg = startIdx(i):endIdx(i);
        [~, k] = max(absRoll(seg));
        idxPeak = seg(k);
        valPeak = rollSm(idxPeak);

        if abs(valPeak) >= cfg.minPeakAbsRoll
            candIdx(end+1,1) = idxPeak; %#ok<AGROW>
            candVal(end+1,1) = valPeak; %#ok<AGROW>
        end
    end

    if isempty(candIdx)
        out.count = 0;
        out.idx = [];
        out.tPeaks = [];
        out.values = [];
        out.features.rollSm = rollSm;
        out.features.yawRateSm = yawRateSm;
        out.features.gyroNormSm = gyroNormSm;
        out.features.speedSm = speedSm;
        out.features.mask = mask;
        return;
    end

    minDistSamples = max(1, round(cfg.minPeakDistanceSec * Fs));

    keep = [];
    current = 1;
    for k = 2:numel(candIdx)
        if (candIdx(k) - candIdx(current)) < minDistSamples
            if abs(candVal(k)) > abs(candVal(current))
                current = k;
            end
        else
            keep(end+1,1) = current; %#ok<AGROW>
            current = k;
        end
    end
    keep(end+1,1) = current;

    idxKeep = candIdx(keep);
    valKeep = candVal(keep);

    if cfg.enforceAlternation
        altKeep = enforceAlternatingSides(valKeep);
        idxKeep = idxKeep(altKeep);
        valKeep = valKeep(altKeep);
    end

    out.count = numel(idxKeep);
    out.idx = idxKeep;
    out.tPeaks = t(idxKeep);
    out.values = valKeep;
    out.features.rollSm = rollSm;
    out.features.yawRateSm = yawRateSm;
    out.features.gyroNormSm = gyroNormSm;
    out.features.speedSm = speedSm;
    out.features.mask = mask;

    if doPlot
        figure('Name','Turn detection with speed','NumberTitle','off');
        tiledlayout(5,1,'Padding','compact','TileSpacing','compact');

        nexttile
        plot(t, roll, 'Color', [0.75 0.75 0.75]); hold on
        plot(t, rollSm, 'b', 'LineWidth', 1.5)
        yline(cfg.rollThresh, '--r'); yline(-cfg.rollThresh, '--r');
        if ~isempty(idxKeep)
            plot(t(idxKeep), valKeep, 'ro', 'MarkerFaceColor', 'r');
        end
        grid on
        ylabel('roll')

        nexttile
        plot(t, yawRateSm, 'm', 'LineWidth', 1.3); hold on
        yline(cfg.yawRateThresh, '--k'); yline(-cfg.yawRateThresh, '--k');
        grid on
        ylabel('yawRate')

        nexttile
        plot(t, gyroNormSm, 'LineWidth', 1.3); hold on
        yline(cfg.gyroNormThresh, '--k');
        grid on
        ylabel('gyroNorm')

        nexttile
        plot(t, speedSm, 'LineWidth', 1.3); hold on
        yline(cfg.speedThresh, '--k');
        grid on
        ylabel('speed')

        nexttile
        stairs(t, double(mask), 'LineWidth', 1.3); hold on
        if ~isempty(idxKeep)
            stem(t(idxKeep), ones(size(idxKeep)), 'filled');
        end
        ylim([-0.1 1.2])
        grid on
        ylabel('mask')
        xlabel('Time [s]')
    end
end

function cfg = fillDefaults(cfg)
    if ~isfield(cfg,'rollSmoothSec'),      cfg.rollSmoothSec = 0.12; end
    if ~isfield(cfg,'yawRateSmoothSec'),   cfg.yawRateSmoothSec = 0.12; end
    if ~isfield(cfg,'gyroSmoothSec'),      cfg.gyroSmoothSec = 0.12; end
    if ~isfield(cfg,'speedSmoothSec'),     cfg.speedSmoothSec = 0.30; end

    if ~isfield(cfg,'rollThresh'),         cfg.rollThresh = 12; end
    if ~isfield(cfg,'yawRateThresh'),      cfg.yawRateThresh = 25; end
    if ~isfield(cfg,'gyroNormThresh'),     cfg.gyroNormThresh = 40; end
    if ~isfield(cfg,'speedThresh'),        cfg.speedThresh = 3.5; end   % m/s default

    if ~isfield(cfg,'minVotes'),           cfg.minVotes = 3; end
    if ~isfield(cfg,'requireRoll'),        cfg.requireRoll = true; end
    if ~isfield(cfg,'requireSpeed'),       cfg.requireSpeed = false; end

    if ~isfield(cfg,'minRegionSec'),       cfg.minRegionSec = 0.15; end
    if ~isfield(cfg,'minPeakAbsRoll'),     cfg.minPeakAbsRoll = 15; end
    if ~isfield(cfg,'minPeakDistanceSec'), cfg.minPeakDistanceSec = 0.45; end
    if ~isfield(cfg,'enforceAlternation'), cfg.enforceAlternation = true; end
end

function maskOut = removeShortTrueRegions(maskIn, minLen)
    d = diff([false; maskIn(:); false]);
    s = find(d == 1);
    e = find(d == -1) - 1;

    maskOut = false(size(maskIn));
    for i = 1:numel(s)
        if (e(i) - s(i) + 1) >= minLen
            maskOut(s(i):e(i)) = true;
        end
    end
end

function keep = enforceAlternatingSides(values)
    if isempty(values)
        keep = [];
        return;
    end

    keep = true(size(values));
    i = 1;
    while i < numel(values)
        if keep(i) && sign(values(i)) == sign(values(i+1))
            if abs(values(i)) >= abs(values(i+1))
                keep(i+1) = false;
            else
                keep(i) = false;
            end
        end
        i = i + 1;
    end
end


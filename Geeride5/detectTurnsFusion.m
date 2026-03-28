function out = detectTurnsFusion(t, euler, gyro, cfg, doPlot)
% Robust turn detection from Euler + gyro
%
% INPUTS:
%   t      - Nx1 time [s]
%   euler  - Nx3 [roll pitch yaw] in deg
%   gyro   - Nx3 angular velocity (same axis order as euler)
%   cfg    - optional struct with thresholds
%   doPlot - true/false
%
% OUTPUT:
%   out.count
%   out.idx
%   out.tPeaks
%   out.values
%   out.side
%   out.sideLabel
%   out.events
%   out.features
%
% Strategy:
%   1) smooth roll, yawRate, gyroNorm
%   2) build candidate mask from multiple conditions
%   3) find contiguous candidate regions
%   4) in each region keep one strongest |roll| extremum
%   5) suppress too-close events
%   6) optionally enforce sign alternation

    if nargin < 4 || isempty(cfg)
        cfg = struct;
    end
    if nargin < 5
        doPlot = false;
    end

    cfg = fillDefaults(cfg);

    t = t(:);
    roll = euler(:,1);
    pitch = euler(:,2); %#ok<NASGU>
    yaw  = euler(:,3);

    roll = roll(:);
    yaw  = yaw(:);

    if size(gyro,2) < 3
        error('gyro must be Nx3');
    end

    gyro = double(gyro);
    gyroX = gyro(:,1);
    gyroY = gyro(:,2);
    gyroZ = gyro(:,3);

    if numel(t) ~= numel(roll) || size(gyro,1) ~= numel(t)
        error('t, euler, gyro must have matching lengths');
    end

    dt = median(diff(t));
    Fs = 1 / dt;

    % -----------------------------
    % features
    % -----------------------------
    yawUnwrap = rad2deg(unwrap(deg2rad(yaw)));
    yawRateFromYaw = gradient(yawUnwrap, t);   % deg/s

    gyroNorm = sqrt(gyroX.^2 + gyroY.^2 + gyroZ.^2);

    nRoll = max(1, round(cfg.rollSmoothSec * Fs));
    nYaw  = max(1, round(cfg.yawRateSmoothSec * Fs));
    nGyro = max(1, round(cfg.gyroSmoothSec * Fs));

    rollSm    = smoothdata(roll,          'movmean', nRoll);
    yawRateSm = smoothdata(yawRateFromYaw,'movmean', nYaw);
    gyroNormSm= smoothdata(gyroNorm,      'movmean', nGyro);

    absRoll    = abs(rollSm);
    absYawRate = abs(yawRateSm);

    % -----------------------------
    % candidate mask
    % -----------------------------
    condRoll = absRoll >= cfg.rollThresh;
    condYaw  = absYawRate >= cfg.yawRateThresh;
    condGyro = gyroNormSm >= cfg.gyroNormThresh;

    % 2-of-3 voting
    voteCount = double(condRoll) + double(condYaw) + double(condGyro);
    mask = voteCount >= cfg.minVotes;

    % optional stronger core condition
    if cfg.requireRoll
        mask = mask & condRoll;
    end

    % remove very short candidate regions
    minRegionSamples = max(1, round(cfg.minRegionSec * Fs));
    mask = removeShortTrueRegions(mask, minRegionSamples);

    % contiguous candidate regions
    d = diff([false; mask; false]);
    startIdx = find(d == 1);
    endIdx   = find(d == -1) - 1;

    % -----------------------------
    % choose one extremum per region
    % -----------------------------
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
        out = makeEmptyOutput(rollSm, yawRateSm, gyroNormSm, mask);
        if doPlot
            doFusionPlot(t, roll, rollSm, yawRateSm, gyroNormSm, mask, out, cfg);
        end
        return;
    end

    % -----------------------------
    % suppress peaks too close
    % -----------------------------
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

    % -----------------------------
    % optional sign alternation
    % -----------------------------
    if cfg.enforceAlternation
        altKeep = enforceAlternatingSides(valKeep);
        idxKeep = idxKeep(altKeep);
        valKeep = valKeep(altKeep);
    end

    % -----------------------------
    % build events
    % -----------------------------
    events = struct( ...
        'idxPeak', {}, 'tPeak', {}, 'value', {}, 'absValue', {}, ...
        'side', {}, 'sideLabel', {}, ...
        'idxStart', {}, 'idxEnd', {}, ...
        'tStart', {}, 'tEnd', {}, 'duration', {}, ...
        'peakYawRate', {}, 'peakGyroNorm', {});

    for k = 1:numel(idxKeep)
        iPeak = idxKeep(k);

        iStart = iPeak;
        while iStart > 1 && mask(iStart)
            iStart = iStart - 1;
        end

        iEnd = iPeak;
        while iEnd < numel(mask) && mask(iEnd)
            iEnd = iEnd + 1;
        end

        sgn = sign(valKeep(k));
        if sgn >= 0
            sgn = 1;
            label = "positive";
        else
            label = "negative";
        end

        events(k).idxPeak      = iPeak;
        events(k).tPeak        = t(iPeak);
        events(k).value        = valKeep(k);
        events(k).absValue     = abs(valKeep(k));
        events(k).side         = sgn;
        events(k).sideLabel    = label;
        events(k).idxStart     = iStart;
        events(k).idxEnd       = iEnd;
        events(k).tStart       = t(iStart);
        events(k).tEnd         = t(iEnd);
        events(k).duration     = t(iEnd) - t(iStart);
        events(k).peakYawRate  = yawRateSm(iPeak);
        events(k).peakGyroNorm = gyroNormSm(iPeak);
    end

    side = sign(valKeep);
    side(side == 0) = 1;

    sideLabel = strings(numel(side),1);
    sideLabel(side > 0) = "positive";
    sideLabel(side < 0) = "negative";

    out.count     = numel(idxKeep);
    out.idx       = idxKeep;
    out.tPeaks    = t(idxKeep);
    out.values    = valKeep;
    out.side      = side;
    out.sideLabel = sideLabel;
    out.events    = events;

    out.features.rollSm     = rollSm;
    out.features.yawRateSm  = yawRateSm;
    out.features.gyroNormSm = gyroNormSm;
    out.features.mask       = mask;
    out.features.voteCount  = voteCount;
    out.features.absRoll    = absRoll;
    out.features.absYawRate = absYawRate;

    if doPlot
        doFusionPlot(t, roll, rollSm, yawRateSm, gyroNormSm, mask, out, cfg);
    end
end


function cfg = fillDefaults(cfg)
    if ~isfield(cfg,'rollSmoothSec'),       cfg.rollSmoothSec = 0.12; end
    if ~isfield(cfg,'yawRateSmoothSec'),    cfg.yawRateSmoothSec = 0.12; end
    if ~isfield(cfg,'gyroSmoothSec'),       cfg.gyroSmoothSec = 0.12; end

    if ~isfield(cfg,'rollThresh'),          cfg.rollThresh = 20; end        % deg
    if ~isfield(cfg,'yawRateThresh'),       cfg.yawRateThresh = 25; end     % deg/s
    if ~isfield(cfg,'gyroNormThresh'),      cfg.gyroNormThresh = 40; end    % depends on units

    if ~isfield(cfg,'minVotes'),            cfg.minVotes = 2; end
    if ~isfield(cfg,'requireRoll'),         cfg.requireRoll = true; end

    if ~isfield(cfg,'minRegionSec'),        cfg.minRegionSec = 0.15; end
    if ~isfield(cfg,'minPeakAbsRoll'),      cfg.minPeakAbsRoll = 15; end
    if ~isfield(cfg,'minPeakDistanceSec'),  cfg.minPeakDistanceSec = 0.45; end

    if ~isfield(cfg,'enforceAlternation'),  cfg.enforceAlternation = true; end
end


function out = makeEmptyOutput(rollSm, yawRateSm, gyroNormSm, mask)
    out.count     = 0;
    out.idx       = [];
    out.tPeaks    = [];
    out.values    = [];
    out.side      = [];
    out.sideLabel = strings(0,1);
    out.events    = struct([]);

    out.features.rollSm     = rollSm;
    out.features.yawRateSm  = yawRateSm;
    out.features.gyroNormSm = gyroNormSm;
    out.features.mask       = mask;
    out.features.voteCount  = [];
    out.features.absRoll    = abs(rollSm);
    out.features.absYawRate = abs(yawRateSm);
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


function doFusionPlot(t, roll, rollSm, yawRateSm, gyroNormSm, mask, out, cfg)

    figure('Name','Turn detection fusion','NumberTitle','off');

    tiledlayout(4,1,'Padding','compact','TileSpacing','compact');

    % ---------------- roll
    nexttile
    plot(t, roll, 'Color', [0.75 0.75 0.75], 'LineWidth', 1.0); hold on
    plot(t, rollSm, 'b', 'LineWidth', 1.6);
    yline( cfg.rollThresh, '--r');
    yline(-cfg.rollThresh, '--r');

    if out.count > 0
        pos = out.values > 0;
        neg = out.values < 0;
        plot(out.tPeaks(pos), out.values(pos), 'ro', 'MarkerFaceColor', 'r');
        plot(out.tPeaks(neg), out.values(neg), 'go', 'MarkerFaceColor', 'g');

        for k = 1:numel(out.events)
            xline(out.events(k).tStart, '--', 'Color', [0.85 0.85 0.85]);
            xline(out.events(k).tEnd,   '--', 'Color', [0.85 0.85 0.85]);
        end
    end
    grid on
    ylabel('roll [deg]')
    title(sprintf('Detected turns: %d', out.count))

    % ---------------- yaw rate
    nexttile
    plot(t, yawRateSm, 'm', 'LineWidth', 1.4); hold on
    yline( cfg.yawRateThresh, '--k');
    yline(-cfg.yawRateThresh, '--k');
    if out.count > 0
        plot(out.tPeaks, yawRateSm(out.idx), 'ko', 'MarkerFaceColor', 'k');
    end
    grid on
    ylabel('yawRate [deg/s]')

    % ---------------- gyro norm
    nexttile
    plot(t, gyroNormSm, 'LineWidth', 1.4); hold on
    yline(cfg.gyroNormThresh, '--k');
    if out.count > 0
        plot(out.tPeaks, gyroNormSm(out.idx), 'ko', 'MarkerFaceColor', 'k');
    end
    grid on
    ylabel('gyroNorm')

    % ---------------- mask
    nexttile
    stairs(t, double(mask), 'LineWidth', 1.4); hold on
    if out.count > 0
        stem(out.tPeaks, ones(size(out.tPeaks)), 'filled');
    end
    ylim([-0.1 1.2])
    grid on
    ylabel('mask')
    xlabel('Time [s]')
end
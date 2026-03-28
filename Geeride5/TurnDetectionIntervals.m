function out = TurnDetectionIntervals(left, right, gps, cfg, doPlot)

    if nargin < 4 || isempty(cfg)
        cfg = struct;
    end
    if nargin < 5
        doPlot = false;
    end

    cfg = fillDefaults(cfg);

    % ---------------------------------
    % basic checks
    % ---------------------------------
    if ~isfield(left, 't') || ~isfield(left, 'euler') || ~isfield(left, 'gyro')
        error('left must contain fields t, euler, gyro');
    end
    if ~isfield(right, 't') || ~isfield(right, 'euler') || ~isfield(right, 'gyro')
        error('right must contain fields t, euler, gyro');
    end
    if ~isfield(gps, 't') || ~isfield(gps, 'speed')
        error('gps must contain fields t, speed');
    end

    if numel(left.t) ~= numel(right.t) || numel(left.t) ~= numel(gps.t)
        error('left.t, right.t, gps.t must have matching lengths');
    end

    if size(left.euler,2) < 3 || size(right.euler,2) < 3
        error('left.euler and right.euler must be Nx3 [roll pitch yaw]');
    end

    if size(left.gyro,2) < 3 || size(right.gyro,2) < 3
        error('left.gyro and right.gyro must be Nx3');
    end

    t = left.t(:);
    dt = median(diff(t));
    Fs = 1 / dt;

    % ---------------------------------
    % average signals from both skis
    % ---------------------------------
    averageEuler = computeAverageEuler(left.euler, right.euler);
    averageGyro  = 0.5 * (left.gyro + right.gyro);

    % ---------------------------------
    % detect peaks separately on left / right / average
    % ---------------------------------
    [idxL,   valL,   featL]   = detectPeaksFromSignals(left.t,   left.euler,   left.gyro,   gps.speed, cfg);
    [idxR,   valR,   featR]   = detectPeaksFromSignals(right.t,  right.euler,  right.gyro,  gps.speed, cfg);
    [idxAvg, valAvg, featAvg] = detectPeaksFromSignals(t,        averageEuler, averageGyro, gps.speed, cfg);

    % ---------------------------------
    % build intervals ONLY from average peaks
    % ---------------------------------
    intervals = buildPeakIntervals(idxAvg, t, numel(t), Fs, cfg);

    % ---------------------------------
    % output
    % ---------------------------------
    out.count   = numel(idxAvg);
    out.idx     = idxAvg;
    out.tPeaks  = t(idxAvg);
    out.values  = valAvg;
    out.side    = repmat('A', numel(idxAvg), 1);   % A = averaged signal

    out.intervals = intervals;

    out.averageEuler = averageEuler;
    out.averageGyro  = averageGyro;

    out.peaks.left.idx    = idxL;
    out.peaks.left.tPeaks = t(idxL);
    out.peaks.left.values = valL;

    out.peaks.right.idx    = idxR;
    out.peaks.right.tPeaks = t(idxR);
    out.peaks.right.values = valR;

    out.peaks.avg.idx    = idxAvg;
    out.peaks.avg.tPeaks = t(idxAvg);
    out.peaks.avg.values = valAvg;

    out.features.left  = featL;
    out.features.right = featR;
    out.features.avg   = featAvg;

    out.features.mask = featAvg.mask;   % hlavný mask = average mask

    % ---------------------------------
    % plotting
    % ---------------------------------
    if doPlot
        figure('Name','Turn detection from averaged skis','NumberTitle','off');
        tiledlayout(6,1,'Padding','compact','TileSpacing','compact');

        % 1) roll signals + peaks + intervals
        nexttile
        plot(t, left.euler(:,1),  'Color', [0.80 0.85 1.00]); hold on
        plot(t, right.euler(:,1), 'Color', [1.00 0.85 0.85]);
        plot(t, averageEuler(:,1), 'k', 'LineWidth', 1.6)
        plot(t, featAvg.rollSm, 'g', 'LineWidth', 1.2)

        yline(cfg.rollThresh, '--k');
        yline(-cfg.rollThresh, '--k');

        if ~isempty(idxL)
            plot(t(idxL), valL, 'bo', 'MarkerFaceColor', 'b');
        end
        if ~isempty(idxR)
            plot(t(idxR), valR, 'ro', 'MarkerFaceColor', 'r');
        end
        if ~isempty(idxAvg)
            plot(t(idxAvg), valAvg, 'ks', 'MarkerFaceColor', 'g', 'MarkerSize', 7);
        end

        for i = 1:size(intervals.idx,1)
            x1 = t(intervals.idx(i,1));
            x2 = t(intervals.idx(i,2));
            yl = ylim(gca);
            patch([x1 x2 x2 x1], [yl(1) yl(1) yl(2) yl(2)], ...
                  [0.9 1.0 0.9], 'FaceAlpha', 0.15, 'EdgeColor', 'none');
        end
        grid on
        ylabel('roll [deg]')
        legend({'left roll','right roll','avg roll','avg roll sm','\pm thresh','left peaks','right peaks','avg peaks'}, ...
               'Location','best')

        % 2) avg yaw rate smoothed
        nexttile
        plot(t, featL.yawRateSm, 'b', 'LineWidth', 1.0); hold on
        plot(t, featR.yawRateSm, 'r', 'LineWidth', 1.0)
        plot(t, featAvg.yawRateSm, 'g', 'LineWidth', 1.4)
        yline(cfg.yawRateThresh, '--k');
        yline(-cfg.yawRateThresh, '--k');
        grid on
        ylabel('yawRate')

        % 3) avg gyro norm smoothed
        nexttile
        plot(t, featL.gyroNormSm, 'b', 'LineWidth', 1.0); hold on
        plot(t, featR.gyroNormSm, 'r', 'LineWidth', 1.0)
        plot(t, featAvg.gyroNormSm, 'g', 'LineWidth', 1.4)
        yline(cfg.gyroNormThresh, '--k');
        grid on
        ylabel('gyroNorm')

        % 4) speed
        nexttile
        plot(t, featAvg.speedSm, 'k', 'LineWidth', 1.2); hold on
        yline(cfg.speedThresh, '--k');
        grid on
        ylabel('speed')

        % 5) average mask
        nexttile
        stairs(t, double(featAvg.mask), 'LineWidth', 1.3); hold on
        if ~isempty(idxAvg)
            stem(t(idxAvg), ones(size(idxAvg)), 'filled');
        end
        ylim([-0.1 1.2])
        grid on
        ylabel('avg mask')

        % 6) interval mask
        nexttile
        intervalMask = false(size(t));
        for i = 1:size(intervals.idx,1)
            intervalMask(intervals.idx(i,1):intervals.idx(i,2)) = true;
        end
        stairs(t, double(intervalMask), 'g', 'LineWidth', 1.5); hold on
        if ~isempty(idxAvg)
            stem(t(idxAvg), ones(size(idxAvg)), 'filled');
        end
        ylim([-0.1 1.2])
        grid on
        ylabel('intervals')
        xlabel('Time [s]')
    end
end


function [idxKeep, valKeep, feat] = detectPeaksFromSignals(t, euler, gyro, speed, cfg)

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
    Fs = 1 / dt;

    yawUnwrap = rad2deg(unwrap(deg2rad(yaw)));
    yawRate = gradient(yawUnwrap, t);
    gyroNorm = sqrt(gyroX.^2 + gyroY.^2 + gyroZ.^2);

    nRoll  = max(1, round(cfg.rollSmoothSec    * Fs));
    nYaw   = max(1, round(cfg.yawRateSmoothSec * Fs));
    nGyro  = max(1, round(cfg.gyroSmoothSec    * Fs));
    nSpeed = max(1, round(cfg.speedSmoothSec   * Fs));

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
        idxKeep = [];
        valKeep = [];

        feat.rollSm = rollSm;
        feat.yawRateSm = yawRateSm;
        feat.gyroNormSm = gyroNormSm;
        feat.speedSm = speedSm;
        feat.mask = mask;
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

    feat.rollSm = rollSm;
    feat.yawRateSm = yawRateSm;
    feat.gyroNormSm = gyroNormSm;
    feat.speedSm = speedSm;
    feat.mask = mask;
end


function averageEuler = computeAverageEuler(eulerL, eulerR)

    if size(eulerL,1) ~= size(eulerR,1) || size(eulerL,2) < 3 || size(eulerR,2) < 3
        error('eulerL and eulerR must be Nx3 with matching length');
    end

    rollAvg  = 0.5 * (eulerL(:,1) + eulerR(:,1));
    pitchAvg = 0.5 * (eulerL(:,2) + eulerR(:,2));

    yawL = deg2rad(eulerL(:,3));
    yawR = deg2rad(eulerR(:,3));

    yawAvg = atan2( sin(yawL) + sin(yawR), ...
                    cos(yawL) + cos(yawR) );
    yawAvg = rad2deg(yawAvg);

    averageEuler = [rollAvg, pitchAvg, yawAvg];
end


function cfg = fillDefaults(cfg)
    if ~isfield(cfg,'rollSmoothSec'),         cfg.rollSmoothSec = 0.12; end
    if ~isfield(cfg,'yawRateSmoothSec'),      cfg.yawRateSmoothSec = 0.12; end
    if ~isfield(cfg,'gyroSmoothSec'),         cfg.gyroSmoothSec = 0.12; end
    if ~isfield(cfg,'speedSmoothSec'),        cfg.speedSmoothSec = 0.30; end

    if ~isfield(cfg,'rollThresh'),            cfg.rollThresh = 12; end
    if ~isfield(cfg,'yawRateThresh'),         cfg.yawRateThresh = 25; end
    if ~isfield(cfg,'gyroNormThresh'),        cfg.gyroNormThresh = 40; end
    if ~isfield(cfg,'speedThresh'),           cfg.speedThresh = 3.5; end

    if ~isfield(cfg,'minVotes'),              cfg.minVotes = 2; end
    if ~isfield(cfg,'requireRoll'),           cfg.requireRoll = true; end
    if ~isfield(cfg,'requireSpeed'),          cfg.requireSpeed = false; end

    if ~isfield(cfg,'minRegionSec'),          cfg.minRegionSec = 0.15; end
    if ~isfield(cfg,'minPeakAbsRoll'),        cfg.minPeakAbsRoll = 15; end
    if ~isfield(cfg,'minPeakDistanceSec'),    cfg.minPeakDistanceSec = 0.45; end
    if ~isfield(cfg,'enforceAlternation'),    cfg.enforceAlternation = true; end

    if ~isfield(cfg,'intervalMinPeaks'),      cfg.intervalMinPeaks = 4; end
    if ~isfield(cfg,'intervalWindowSec'),     cfg.intervalWindowSec = 20; end
    if ~isfield(cfg,'intervalPadBeforeSec'),  cfg.intervalPadBeforeSec = 10; end
    if ~isfield(cfg,'intervalPadAfterSec'),   cfg.intervalPadAfterSec = 20; end
    if ~isfield(cfg,'intervalMergeGapSec'),   cfg.intervalMergeGapSec = 1.5; end
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


function intervals = buildPeakIntervals(peakIdx, t, nSamples, Fs, cfg)
    intervals.idx = zeros(0,2);
    intervals.t = zeros(0,2);
    intervals.countPeaks = [];
    intervals.peakIdx = {};

    if isempty(peakIdx)
        return;
    end

    padBefore = round(cfg.intervalPadBeforeSec * Fs);
    padAfter  = round(cfg.intervalPadAfterSec  * Fs);
    mergeGap  = round(cfg.intervalMergeGapSec  * Fs);

    N = cfg.intervalMinPeaks;
    W = cfg.intervalWindowSec;

    rawIntervals = [];
    peakGroups = {};

    i = 1;
    while i <= numel(peakIdx) - N + 1
        j = i + N - 1;

        if (t(peakIdx(j)) - t(peakIdx(i))) <= W
            k = j;

            while k < numel(peakIdx)
                if (t(peakIdx(k+1)) - t(peakIdx(i)) <= W) || ...
                   (t(peakIdx(k+1)) - t(peakIdx(k)) <= W)
                    k = k + 1;
                else
                    break;
                end
            end

            sIdx = max(1, peakIdx(i) - padBefore);
            eIdx = min(nSamples, peakIdx(k) + padAfter);

            rawIntervals(end+1,:) = [sIdx eIdx]; %#ok<AGROW>
            peakGroups{end+1,1} = peakIdx(i:k); %#ok<AGROW>

            i = k + 1;
        else
            i = i + 1;
        end
    end

    if isempty(rawIntervals)
        return;
    end

    merged = rawIntervals(1,:);
    mergedGroups = peakGroups(1);

    for m = 2:size(rawIntervals,1)
        if rawIntervals(m,1) <= merged(end,2) + mergeGap
            merged(end,2) = max(merged(end,2), rawIntervals(m,2));
            mergedGroups{end,1} = [mergedGroups{end}; peakGroups{m}];
        else
            merged(end+1,:) = rawIntervals(m,:); %#ok<AGROW>
            mergedGroups{end+1,1} = peakGroups{m}; %#ok<AGROW>
        end
    end

    for m = 1:numel(mergedGroups)
        mergedGroups{m} = unique(mergedGroups{m}, 'stable');
    end

    intervals.idx = merged;
    intervals.t = [t(merged(:,1)) t(merged(:,2))];
    intervals.countPeaks = cellfun(@numel, mergedGroups);
    intervals.peakIdx = mergedGroups;
end
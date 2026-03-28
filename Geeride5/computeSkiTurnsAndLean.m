function out = computeSkiTurnsAndLean(t, rollDeg, cfg)
% Compute number of ski turns and maximum lean from roll signal
%
% INPUTS:
%   t        - Nx1 time [s]
%   rollDeg  - Nx1 roll angle [deg]
%   cfg      - optional config struct
%
% OUTPUT:
%   out.turnCount             - number of detected turns
%   out.maxLeanDegAbs         - max absolute lean [deg]
%   out.maxRightLeanDeg       - max positive roll [deg]
%   out.maxLeftLeanDeg        - max negative roll magnitude [deg]
%   out.peakIdx               - indices of accepted extrema
%   out.peakTimes             - times of accepted extrema
%   out.peakValuesDeg         - roll values of accepted extrema
%   out.rollSmoothDeg         - smoothed roll
%   out.cfg                   - config used

    t = t(:);
    rollDeg = rollDeg(:);

    if nargin < 3
        cfg = struct;
    end
    cfg = fillDefaults(cfg);

    if numel(t) ~= numel(rollDeg)
        error('t and rollDeg must have same length.');
    end

    if numel(t) < 5
        error('Signal too short.');
    end

    dt = median(diff(t));
    Fs = 1 / dt;

    % -------- smooth roll
    smoothWin = max(3, round(cfg.smoothSec * Fs));
    if mod(smoothWin,2) == 0
        smoothWin = smoothWin + 1;
    end

    rollSmooth = smoothdata(rollDeg, 'movmean', smoothWin);

    % -------- max lean
    maxLeanDegAbs   = max(abs(rollSmooth), [], 'omitnan');
    maxRightLeanDeg = max(rollSmooth, [], 'omitnan');
    maxLeftLeanDeg  = abs(min(rollSmooth, [], 'omitnan'));

    % -------- find peaks and valleys
    minPeakDistSamples = max(1, round(cfg.minPeakDistanceSec * Fs));

    [pksMax, locMax] = findpeaks(rollSmooth, ...
        'MinPeakProminence', cfg.minProminenceDeg, ...
        'MinPeakDistance',   minPeakDistSamples, ...
        'MinPeakHeight',     cfg.minAbsPeakDeg);

    [pksMinNeg, locMin] = findpeaks(-rollSmooth, ...
        'MinPeakProminence', cfg.minProminenceDeg, ...
        'MinPeakDistance',   minPeakDistSamples, ...
        'MinPeakHeight',     cfg.minAbsPeakDeg);

    pksMin = -pksMinNeg;

    % -------- merge extrema
    allLocs = [locMax; locMin];
    allVals = [pksMax; pksMin];

    [allLocs, order] = sort(allLocs);
    allVals = allVals(order);

    % -------- keep alternating extrema only
    keepLocs = [];
    keepVals = [];

    for i = 1:numel(allLocs)
        curLoc = allLocs(i);
        curVal = allVals(i);

        if isempty(keepLocs)
            keepLocs(end+1,1) = curLoc; %#ok<AGROW>
            keepVals(end+1,1) = curVal; %#ok<AGROW>
            continue;
        end

        prevVal = keepVals(end);

        % same sign -> keep stronger one
        if sign(curVal) == sign(prevVal)
            if abs(curVal) > abs(prevVal)
                keepLocs(end) = curLoc;
                keepVals(end) = curVal;
            end
        else
            % opposite sign -> new turn candidate
            if abs(curVal - prevVal) >= cfg.minTurnAmplitudeDeg
                keepLocs(end+1,1) = curLoc; %#ok<AGROW>
                keepVals(end+1,1) = curVal; %#ok<AGROW>
            end
        end
    end

    % -------- turn count
    % každé striedanie strany zodpovedá ďalšiemu oblúku
    if numel(keepVals) >= 2
        turnCount = numel(keepVals) - 1;
    else
        turnCount = 0;
    end

    % -------- output
    out.turnCount       = turnCount;
    out.maxLeanDegAbs   = maxLeanDegAbs;
    out.maxRightLeanDeg = maxRightLeanDeg;
    out.maxLeftLeanDeg  = maxLeftLeanDeg;
    out.peakIdx         = keepLocs;
    out.peakTimes       = t(keepLocs);
    out.peakValuesDeg   = keepVals;
    out.rollSmoothDeg   = rollSmooth;
    out.cfg             = cfg;
end


function cfg = fillDefaults(cfg)
    if ~isfield(cfg, 'smoothSec'),           cfg.smoothSec = 0.20; end
    if ~isfield(cfg, 'minProminenceDeg'),    cfg.minProminenceDeg = 10; end
    if ~isfield(cfg, 'minAbsPeakDeg'),       cfg.minAbsPeakDeg = 15; end
    if ~isfield(cfg, 'minPeakDistanceSec'),  cfg.minPeakDistanceSec = 0.50; end
    if ~isfield(cfg, 'minTurnAmplitudeDeg'), cfg.minTurnAmplitudeDeg = 20; end
end
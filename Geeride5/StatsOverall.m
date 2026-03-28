function out = StatsOverall(Turndetection, right, left, gps, tLeft, tRight)

    if nargin < 5
        tLeft = [];
    end
    if nargin < 6
        tRight = [];
    end

    out = struct();

    % default values
    out.maxspeed = 0;
    out.avrgspeed = 0;

    out.maxPeakL = 0;
    out.maxPeakR = 0;
    out.averagePeakR = 0;
    out.averagePeakL = 0;

    out.maxG = 0;
    out.averageG = 0;

    out.distance = 0;
    out.elevationgain = 0;
    out.elevationloss = 0;

    out.runCount = 0;
    out.turnCount = 0;
    out.averageTurnLength = 0;

    % nove turn stats
    out.averageTurnDuration = 0;
    out.maxTurnDuration = 0;
    out.minTurnDuration = 0;

    out.averageTurnLengthGPS = 0;
    out.maxTurnLengthGPS = 0;
    out.minTurnLengthGPS = 0;

    out.averageTurnSpeed = 0;
    out.maxTurnSpeed = 0;
    out.minTurnSpeed = 0;

    % speed stats
    if ~isempty(gps) && isfield(gps, 'speed') && ~isempty(gps.speed)
        out.maxspeed = max(gps.speed * 3.6, [], 'omitnan');
        out.avrgspeed = mean(gps.speed * 3.6, 'omitnan');
    end

    % left edge angle
    if ~isempty(left) && isfield(left, 'euler') && ~isempty(left.euler) && ...
       isfield(Turndetection, 'peaks') && isfield(Turndetection.peaks, 'left') && ...
       isfield(Turndetection.peaks.left, 'values') && ~isempty(Turndetection.peaks.left.values)

        edgeAngleL = abs(Turndetection.peaks.left.values);
        out.maxPeakL = max(edgeAngleL, [], 'omitnan');
        out.averagePeakL = mean(edgeAngleL, 'omitnan');
    end

    % right edge angle
    if ~isempty(right) && isfield(right, 'euler') && ~isempty(right.euler) && ...
       isfield(Turndetection, 'peaks') && isfield(Turndetection.peaks, 'right') && ...
       isfield(Turndetection.peaks.right, 'values') && ~isempty(Turndetection.peaks.right.values)

        edgeAngleR = abs(Turndetection.peaks.right.values);
        out.maxPeakR = max(edgeAngleR, [], 'omitnan');
        out.averagePeakR = mean(edgeAngleR, 'omitnan');
    end

    % G-force stats
    if ~isempty(right) && isfield(right, 'acc') && ~isempty(right.acc)
        g = sqrt(sum(right.acc.^2, 2)) / 9.81;
        out.maxG = max(g, [], 'omitnan');
        out.averageG = mean(g, 'omitnan');
    end

    % distance
    if ~isempty(gps) && isfield(gps, 'latitude') && isfield(gps, 'longitude') && ...
            ~isempty(gps.latitude) && ~isempty(gps.longitude)
        cumDist_m = computeCumulativeDistanceFromGPS(gps.latitude, gps.longitude);
        if ~isempty(cumDist_m)
            out.distance = cumDist_m(end) / 1000;   % km
        end
    end

    % elevation gain
    if ~isempty(gps) && isfield(gps, 'altitude') && ~isempty(gps.altitude)
        cumGain_m = computeCumulativeElevationGain(gps.altitude);
        if ~isempty(cumGain_m)
            out.elevationgain = cumGain_m(end);     % m
        end
    end

    % elevation loss
    if ~isempty(gps) && isfield(gps, 'altitude') && ~isempty(gps.altitude)
        cumLoss_m = computeCumulativeElevationLoss(gps.altitude);
        if ~isempty(cumLoss_m)
            out.elevationloss = cumLoss_m(end);     % m
        end
    end

    % turn count = peaky v danom useku
    if ~isempty(Turndetection) && isfield(Turndetection, 'count') && ~isempty(Turndetection.count)
        out.turnCount = Turndetection.count;
    end

    % stare averageTurnLength nech ostane ako priemerna dlzka intervalov, 
    % ale uz z prieniku useku detailed a peakZeroTimes intervalov
    [turnIntervals] = buildTurnIntervalsInCurrentWindow(tLeft, tRight, right, gps);

    if ~isempty(turnIntervals)
        turnDurations = turnIntervals(:,2) - turnIntervals(:,1);

        out.averageTurnLength = mean(turnDurations, 'omitnan');

        out.averageTurnDuration = mean(turnDurations, 'omitnan');
        out.maxTurnDuration = max(turnDurations, [], 'omitnan');
        out.minTurnDuration = min(turnDurations, [], 'omitnan');

        [out.averageTurnLengthGPS, out.maxTurnLengthGPS, out.minTurnLengthGPS] = ...
            computeTurnLengthGPSStatsFromIntervals(turnIntervals, gps);

        [out.averageTurnSpeed, out.maxTurnSpeed, out.minTurnSpeed] = ...
            computeTurnSpeedStatsFromIntervals(turnIntervals, gps);
    end

    % run count
    if ~isempty(gps) && isfield(gps, 't') && ~isempty(gps.t) && ...
       isfield(gps, 'altitude') && ~isempty(gps.altitude)
        out.runCount = compute_runCount(gps);
    end

end


function cumDist_m = computeCumulativeDistanceFromGPS(latitude, longitude)

    R = 6371000;

    lat = deg2rad(latitude(:));
    lon = deg2rad(longitude(:));

    dlat = diff(lat);
    dlon = diff(lon);

    a = sin(dlat/2).^2 + cos(lat(1:end-1)) .* cos(lat(2:end)) .* sin(dlon/2).^2;
    c = 2 * atan2(sqrt(a), sqrt(1-a));

    segmentDist = R * c;
    cumDist_m = [0; cumsum(segmentDist, 'omitnan')];
end


function cumLoss_m = computeCumulativeElevationLoss(altitude)
    alt = altitude(:);
    alt = fillmissing(alt, 'linear', 'EndValues', 'nearest');

    dAlt = diff(alt);
    loss = max(-dAlt, 0);

    cumLoss_m = [0; cumsum(loss, 'omitnan')];
end

function [maxEdgeAngle, avgEdgeAngle] = computeEdgeAngleStats(data)

    maxEdgeAngle = 0;
    avgEdgeAngle = 0;

    if ~isempty(data) && isfield(data, 'euler') && ~isempty(data.euler)
        edgeAngle = abs(data.euler(:,1));   % roll = edge angle
        maxEdgeAngle = max(edgeAngle, [], 'omitnan');
        avgEdgeAngle = mean(edgeAngle, 'omitnan');
    end
end


function [avgTurnLength] = computeTurnLengthStats(Turndetection)

    avgTurnLength = 0;

    if ~isempty(Turndetection) && ...
       isfield(Turndetection, 'intervals') && ...
       isfield(Turndetection.intervals, 't') && ...
       ~isempty(Turndetection.intervals.t)

        turnLengths = Turndetection.intervals.t(:,2) - Turndetection.intervals.t(:,1);


        avgTurnLength = mean(turnLengths, 'omitnan');
    end
end

function cumGain_m = computeCumulativeElevationGain(altitude)

    alt = altitude(:);
    alt = fillmissing(alt, 'linear', 'EndValues', 'nearest');

    dAlt = diff(alt);
    gain = max(dAlt, 0);

    cumGain_m = [0; cumsum(gain, 'omitnan')];
end

function runCount = compute_runCount(gps)

    t = gps.t(:);
    alt = movmean(gps.altitude(:), 3000);

    dt = median(diff(t));
    dAltDt = [0; diff(alt)] / dt;

    % jazda = klesanie
    downMask = dAltDt < -0.03;

    % kratka rovina / statie jazdu NEPRERUSI
    maxFlatGapSec = 40;
    maxFlatGapN = round(maxFlatGapSec / dt);

    d = diff([0; downMask; 0]);
    starts = find(d == 1);
    ends   = find(d == -1) - 1;

    for i = 1:numel(starts)-1
        gap = starts(i+1) - ends(i) - 1;
        if gap <= maxFlatGapN
            downMask(ends(i):starts(i+1)) = true;
        end
    end

    % znovu najdi spojene segmenty
    d = diff([0; downMask; 0]);
    starts = find(d == 1);
    ends   = find(d == -1) - 1;

    % odfiltruj kratke "jazdy"
    minRunTime = 30;
    keep = (t(ends) - t(starts)) >= minRunTime;

    starts = starts(keep);
    ends   = ends(keep);

    % odfiltruj segmenty s malym celkovym poklesom
    minDrop = 15; % m
    keep2 = (alt(starts) - alt(ends)) >= minDrop;

    runCount = sum(keep2);
end

function turnIntervals = buildTurnIntervalsInCurrentWindow(tLeft, tRight, right, gps)

    turnIntervals = [];

    if isempty(tLeft) || isempty(tRight)
        return
    end

    % aktualne casove okno = okno uz orezanych dat v detailed
    tMinCandidates = [];
    tMaxCandidates = [];

    if ~isempty(right) && isfield(right, 't') && ~isempty(right.t)
        tMinCandidates(end+1) = right.t(1);
        tMaxCandidates(end+1) = right.t(end);
    end

    if ~isempty(gps) && isfield(gps, 't') && ~isempty(gps.t)
        tMinCandidates(end+1) = gps.t(1);
        tMaxCandidates(end+1) = gps.t(end);
    end

    if isempty(tMinCandidates) || isempty(tMaxCandidates)
        return
    end

    t1 = max(tMinCandidates(1:min(end,numel(tMinCandidates))));
    t2 = min(tMaxCandidates(1:min(end,numel(tMaxCandidates))));

    if t1 >= t2
        return
    end

    n = min(numel(tLeft), numel(tRight));

    for i = 1:n
        a = tLeft(i);
        b = tRight(i);

        if isnan(a) || isnan(b)
            continue
        end

        startInt = max(a, t1);
        stopInt  = min(b, t2);

        if startInt < stopInt
            turnIntervals = [turnIntervals; startInt stopInt];
        end
    end
end

function [avgTurnLengthGPS, maxTurnLengthGPS, minTurnLengthGPS] = computeTurnLengthGPSStatsFromIntervals(turnIntervals, gps)

    avgTurnLengthGPS = 0;
    maxTurnLengthGPS = 0;
    minTurnLengthGPS = 0;

    if isempty(turnIntervals) || isempty(gps) || ...
       ~isfield(gps, 't') || isempty(gps.t) || ...
       ~isfield(gps, 'latitude') || isempty(gps.latitude) || ...
       ~isfield(gps, 'longitude') || isempty(gps.longitude)
        return
    end

    nInt = size(turnIntervals, 1);
    turnLengths = NaN(nInt,1);

    for i = 1:nInt
        t1 = turnIntervals(i,1);
        t2 = turnIntervals(i,2);

        mask = gps.t >= t1 & gps.t <= t2;

        if sum(mask) >= 2
            cumDist_m = computeCumulativeDistanceFromGPS(gps.latitude(mask), gps.longitude(mask));
            if ~isempty(cumDist_m)
                turnLengths(i) = cumDist_m(end);   % m
            end
        end
    end

    good = ~isnan(turnLengths);
    if any(good)
        avgTurnLengthGPS = mean(turnLengths(good), 'omitnan');
        maxTurnLengthGPS = max(turnLengths(good), [], 'omitnan');
        minTurnLengthGPS = min(turnLengths(good), [], 'omitnan');
    end
end

function [avgTurnSpeed, maxTurnSpeed, minTurnSpeed] = computeTurnSpeedStatsFromIntervals(turnIntervals, gps)

    avgTurnSpeed = 0;
    maxTurnSpeed = 0;
    minTurnSpeed = 0;

    if isempty(turnIntervals) || isempty(gps) || ...
       ~isfield(gps, 't') || isempty(gps.t) || ...
       ~isfield(gps, 'speed') || isempty(gps.speed)
        return
    end

    nInt = size(turnIntervals, 1);
    turnSpeeds = NaN(nInt,1);

    for i = 1:nInt
        t1 = turnIntervals(i,1);
        t2 = turnIntervals(i,2);

        mask = gps.t >= t1 & gps.t <= t2;

        if any(mask)
            turnSpeeds(i) = mean(gps.speed(mask) * 3.6, 'omitnan');   % km/h
        end
    end

    good = ~isnan(turnSpeeds);
    if any(good)
        avgTurnSpeed = mean(turnSpeeds(good), 'omitnan');
        maxTurnSpeed = max(turnSpeeds(good), [], 'omitnan');
        minTurnSpeed = min(turnSpeeds(good), [], 'omitnan');
    end
end
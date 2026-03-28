function out = StatsOverall(Turndetection, right, left, gps)

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

    % speed stats
        out.maxspeed = max(gps.speed*3.6, [], 'omitnan');
        out.avrgspeed = mean(gps.speed*3.6, 'omitnan');

    % left edge angle
    if ~isempty(left) && isfield(left, 'euler') && ~isempty(left.euler)
        edgeAngleL = abs(Turndetection.peaks.left.values);
        out.maxPeakL = max(edgeAngleL, [], 'omitnan');
        out.averagePeakL = mean(edgeAngleL, 'omitnan');
    end

    % right edge angle
    if ~isempty(right) && isfield(right, 'euler') && ~isempty(right.euler)
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
    if ~isempty(gps) && isfield(gps, 'latitude') && isfield(gps, 'longitude') ...
            && ~isempty(gps.latitude) && ~isempty(gps.longitude)
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
        if ~isempty(cumGain_m)
            out.elevatioloss = cumLoss_m(end);     % m
        end
     end
    

    % turn count
    if ~isempty(Turndetection) && isfield(Turndetection, 'count') && ~isempty(Turndetection.count)
        out.turnCount = Turndetection.count;
    end

    [out.averageTurnLength] = computeTurnLengthStats(Turndetection);

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
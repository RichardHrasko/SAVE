function out = turnByTurnDetailed(Turndetection, right, left, gps, tLeft, tRight, folder)

    nTurns = min(numel(tLeft), numel(tRight));

    out = struct();
    out.turns = struct([]);

    for i = 1:nTurns
        t1 = tLeft(i);
        t2 = tRight(i);

        if isnan(t1) || isnan(t2) || t2 <= t1
            continue
        end

        maskR = right.t >= t1 & right.t <= t2;
        maskL = left.t  >= t1 & left.t  <= t2;
        maskG = gps.t   >= t1 & gps.t   <= t2;

        right_i = struct();
        left_i  = struct();
        gps_i   = struct();

        right_i.t = right.t(maskR);
        right_i.euler = right.euler(maskR,:);
        if isfield(right,'q'),    right_i.q = right.q(maskR); end
        if isfield(right,'acc'),  right_i.acc = right.acc(maskR,:); end
        if isfield(right,'gyro'), right_i.gyro = right.gyro(maskR,:); end
        if isfield(right,'mag'),  right_i.mag = right.mag(maskR,:); end
        if isfield(right,'wAcc'), right_i.wAcc = right.wAcc(maskR); end
        if isfield(right,'wMag'), right_i.wMag = right.wMag(maskR); end

        left_i.t = left.t(maskL);
        left_i.euler = left.euler(maskL,:);
        if isfield(left,'q'),    left_i.q = left.q(maskL); end
        if isfield(left,'acc'),  left_i.acc = left.acc(maskL,:); end
        if isfield(left,'gyro'), left_i.gyro = left.gyro(maskL,:); end
        if isfield(left,'mag'),  left_i.mag = left.mag(maskL,:); end
        if isfield(left,'wAcc'), left_i.wAcc = left.wAcc(maskL); end
        if isfield(left,'wMag'), left_i.wMag = left.wMag(maskL); end

        gps_i.t = gps.t(maskG);
        gps_i.latitude = gps.latitude(maskG);
        gps_i.longitude = gps.longitude(maskG);
        gps_i.altitude = gps.altitude(maskG);
        gps_i.accuracy = gps.accuracy(maskG);
        gps_i.bearing = gps.bearing(maskG);
        gps_i.speed = gps.speed(maskG);
        if isfield(gps,'data')
            gps_i.data = gps.data(maskG,:);
        end

        Turndetection_i = struct();

        maskA = Turndetection.tPeaks >= t1 & Turndetection.tPeaks <= t2;
        Turndetection_i.count   = sum(maskA);
        Turndetection_i.tPeaks  = Turndetection.tPeaks(maskA);
        Turndetection_i.idx     = Turndetection.idx(maskA);
        Turndetection_i.values  = Turndetection.values(maskA);

        if isfield(Turndetection,'side')
            Turndetection_i.side = Turndetection.side(maskA);
        end

        if isfield(Turndetection,'peaks') && isfield(Turndetection.peaks,'left')
            maskPL = Turndetection.peaks.left.tPeaks >= t1 & Turndetection.peaks.left.tPeaks <= t2;
            Turndetection_i.peaks.left.tPeaks = Turndetection.peaks.left.tPeaks(maskPL);
            Turndetection_i.peaks.left.idx    = Turndetection.peaks.left.idx(maskPL);
            Turndetection_i.peaks.left.values = Turndetection.peaks.left.values(maskPL);
        else
            Turndetection_i.peaks.left.tPeaks = [];
            Turndetection_i.peaks.left.idx    = [];
            Turndetection_i.peaks.left.values = [];
        end

        if isfield(Turndetection,'peaks') && isfield(Turndetection.peaks,'right')
            maskPR = Turndetection.peaks.right.tPeaks >= t1 & Turndetection.peaks.right.tPeaks <= t2;
            Turndetection_i.peaks.right.tPeaks = Turndetection.peaks.right.tPeaks(maskPR);
            Turndetection_i.peaks.right.idx    = Turndetection.peaks.right.idx(maskPR);
            Turndetection_i.peaks.right.values = Turndetection.peaks.right.values(maskPR);
        else
            Turndetection_i.peaks.right.tPeaks = [];
            Turndetection_i.peaks.right.idx    = [];
            Turndetection_i.peaks.right.values = [];
        end

        if isfield(Turndetection,'peaks') && isfield(Turndetection.peaks,'avg')
            maskPA = Turndetection.peaks.avg.tPeaks >= t1 & Turndetection.peaks.avg.tPeaks <= t2;
            Turndetection_i.peaks.avg.tPeaks = Turndetection.peaks.avg.tPeaks(maskPA);
            Turndetection_i.peaks.avg.idx    = Turndetection.peaks.avg.idx(maskPA);
            Turndetection_i.peaks.avg.values = Turndetection.peaks.avg.values(maskPA);
        else
            Turndetection_i.peaks.avg.tPeaks = [];
            Turndetection_i.peaks.avg.idx    = [];
            Turndetection_i.peaks.avg.values = [];
        end

        if isfield(Turndetection,'averageEuler') && ~isempty(Turndetection.averageEuler)
            Turndetection_i.averageEuler = Turndetection.averageEuler(maskR,:);
        end

        if isfield(Turndetection,'averageGyro') && ~isempty(Turndetection.averageGyro)
            Turndetection_i.averageGyro = Turndetection.averageGyro(maskR,:);
        end

        Turndetection_i.intervals.t = [t1 t2];
        Turndetection_i.count = sum(maskA);

        stats_i = StatsOverall(Turndetection_i, right_i, left_i, gps_i);

        % identifikatory obluku pre presne sparovanie
        stats_i.turnIndex = i;
        stats_i.tStart = t1;
        stats_i.tStop = t2;
        stats_i.duration = t2 - t1;
        stats_i.turnInterval = [t1 t2];

        if isfield(Turndetection,'idx') && numel(Turndetection.idx) >= i
            stats_i.peakIdx = Turndetection.idx(i);
        else
            stats_i.peakIdx = NaN;
        end

        if isfield(Turndetection,'tPeaks') && numel(Turndetection.tPeaks) >= i
            stats_i.tPeak = Turndetection.tPeaks(i);
        else
            stats_i.tPeak = NaN;
        end

        if isfield(Turndetection,'values') && numel(Turndetection.values) >= i
            stats_i.peakValue = Turndetection.values(i);
        else
            stats_i.peakValue = NaN;
        end

        if isfield(Turndetection,'side') && numel(Turndetection.side) >= i
            stats_i.side = string(Turndetection.side(i));
        else
            stats_i.side = "";
        end

        out.turns(i).stats = stats_i;

        if nargin >= 7 && ~isempty(folder)
            exportOverallStatsCSV(stats_i, folder, sprintf('turn_%02d_stats', i));
        end
    end

    out.table = flattenTurnStats(out.turns);

    if nargin >= 7 && ~isempty(folder)
        if ~exist(folder, 'dir')
            mkdir(folder);
        end
        writetable(out.table, fullfile(folder, 'turn_by_turn_stats.csv'));
    end
end


function T = flattenTurnStats(turns)

    if isempty(turns)
        T = table();
        return
    end

    rowStructs = {};
    allNames = {};

    for i = 1:numel(turns)
        if ~isfield(turns(i), 'stats') || isempty(turns(i).stats)
            continue
        end

        s = turns(i).stats;
        r = struct();

        f = fieldnames(s);
        for k = 1:numel(f)
            name = f{k};
            value = s.(name);

            if isnumeric(value) && isscalar(value)
                r.(name) = value;
                allNames{end+1} = name; %#ok<AGROW>

            elseif islogical(value) && isscalar(value)
                r.(name) = double(value);
                allNames{end+1} = name; %#ok<AGROW>

            elseif isstring(value) && isscalar(value)
                r.(name) = value;
                allNames{end+1} = name; %#ok<AGROW>

            elseif ischar(value) && isrow(value)
                r.(name) = string(value);
                allNames{end+1} = name; %#ok<AGROW>

            elseif isnumeric(value) && isequal(size(value), [1 2])
                r.([name '_start']) = value(1);
                r.([name '_stop'])  = value(2);
                allNames{end+1} = [name '_start']; %#ok<AGROW>
                allNames{end+1} = [name '_stop'];  %#ok<AGROW>
            end
        end

        rowStructs{end+1} = r; %#ok<AGROW>
    end

    if isempty(rowStructs)
        T = table();
        return
    end

    allNames = unique(allNames, 'stable');

    for i = 1:numel(rowStructs)
        r = rowStructs{i};

        for k = 1:numel(allNames)
            name = allNames{k};
            if ~isfield(r, name)
                r.(name) = NaN;
            end
        end

        rowStructs{i} = orderfields(r, allNames);
    end

    rows = vertcat(rowStructs{:});
    T = struct2table(rows, 'AsArray', true);
end
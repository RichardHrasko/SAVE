function [tLeft, tRight] = peakZeroTimes(t, Turndetection, exportFolder)

    roll = Turndetection.averageEuler(:,1);
    peakIdx = Turndetection.idx;

    nPeaks = length(peakIdx);
    tLeft  = NaN(nPeaks,1);
    tRight = NaN(nPeaks,1);

    for k = 1:nPeaks
        p = peakIdx(k);

        % hladanie vlavo od peaku
        for i = p-1:-1:1
            if roll(i) * roll(i+1) <= 0
                t1 = t(i);
                t2 = t(i+1);
                y1 = roll(i);
                y2 = roll(i+1);

                tLeft(k) = t1 - y1 * (t2 - t1) / (y2 - y1);
                break
            end
        end

        % hladanie vpravo od peaku
        for i = p:length(roll)-1
            if roll(i) * roll(i+1) <= 0
                t1 = t(i);
                t2 = t(i+1);
                y1 = roll(i);
                y2 = roll(i+1);

                tRight(k) = t1 - y1 * (t2 - t1) / (y2 - y1);
                break
            end
        end
    end

    if nargin >= 3 && ~isempty(exportFolder)
        csvFile = fullfile(exportFolder, "peak_bounds.csv");
        T = table(tLeft, tRight);
        writetable(T, csvFile);
    end
end
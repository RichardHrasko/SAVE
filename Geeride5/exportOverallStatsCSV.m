function exportOverallStatsCSV(stats, folder, name)

    if ~exist(folder, 'dir')
        mkdir(folder);
    end

    T = struct2table(stats, 'AsArray', true);
    writetable(T, fullfile(folder, [name '.csv']));
end
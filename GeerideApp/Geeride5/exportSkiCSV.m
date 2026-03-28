function exportSkiCSV(t, SkiEuler, Acc, Gyro, Mag, folder, fileTag)

if ~isfolder(folder)
    mkdir(folder);
end

T_euler = table(t(:), SkiEuler(:,1), SkiEuler(:,2), SkiEuler(:,3), ...
    'VariableNames', {'time','roll_deg','pitch_deg','yaw_deg'});
writetable(T_euler, fullfile(folder, fileTag + "_euler.csv"));

T_acc = table(t(:), Acc(:,1), Acc(:,2), Acc(:,3), ...
    'VariableNames', {'time','acc_x','acc_y','acc_z'});
writetable(T_acc, fullfile(folder, fileTag + "_acc.csv"));

T_gyro = table(t(:), Gyro(:,1), Gyro(:,2), Gyro(:,3), ...
    'VariableNames', {'time','gyro_x','gyro_y','gyro_z'});
writetable(T_gyro, fullfile(folder, fileTag + "_gyro.csv"));

T_mag = table(t(:), Mag(:,1), Mag(:,2), Mag(:,3), ...
    'VariableNames', {'time','mag_x','mag_y','mag_z'});
writetable(T_mag, fullfile(folder, fileTag + "_mag.csv"));

end
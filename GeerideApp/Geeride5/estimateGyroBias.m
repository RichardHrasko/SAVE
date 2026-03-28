function [ConstantBias] = estimateGyroBias(t, gyro_cal, biasSeconds)

    % --- first N seconds window
    idx = (t - t(1)) <= biasSeconds;

    gyroBias = gyro_cal(idx,:);
    ConstantBias = mean(gyroBias, 1);

    % --- plots
    % figure;
    % plot(t(idx), rad2deg(gyroBias));
    % title(sprintf('Gyro Raw Data (First %.1f Seconds)', biasSeconds));
    % xlabel('time (s)');
    % ylabel('Angular Velocity (deg/s)');
    % legend('wx','wy','wz');
    % grid on;
    % 
    % figure;
    % plot(t(idx), rad2deg(gyroBias - ConstantBias));
    % title(sprintf('Gyro Bias Removed (First %.1f Seconds)', biasSeconds));
    % xlabel('time (s)');
    % ylabel('Angular Velocity (deg/s)');
    % legend('wx','wy','wz');
    % grid on;


    disp("Estimated gyro bias (deg/s):")
    disp(rad2deg(ConstantBias))
end

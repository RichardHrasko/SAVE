function [t_acc, t_gyro, t_mag, gyro, acc, mag] = CSV_Import_lowpass(RawplotsOn,folder)

% -------- find files
accList  = dir(fullfile(folder,"*-Acc.csv"));
baseName = erase(string(accList(1).name),"-Acc.csv");

accFile  = fullfile(folder, baseName + "-Acc.csv");
magFile  = fullfile(folder, baseName + "-Mag.csv");
gyroFile = fullfile(folder, baseName + "-Gyro.csv");

% -------- read
A = readmatrix(accFile,  "Delimiter",";","NumHeaderLines",1);
M = readmatrix(magFile,  "Delimiter",";","NumHeaderLines",1);
G = readmatrix(gyroFile, "Delimiter",";","NumHeaderLines",1);

% -------- time
t_acc  = A(:,1);
t_mag  = M(:,1);
t_gyro = G(:,1);

% -------- coefficients
acc_coeff  = 16/32767;      % g
mag_coeff  = 8/32767;       % gauss
gyro_coeff = 1000/32767;    % deg/s

% -------- convert raw
acc_g    = A(:,2:4) * acc_coeff;
mag_G    = M(:,2:4) * mag_coeff;
gyro_dps = G(:,2:4) * gyro_coeff;

% -------- resample gyro & mag to acc timeline
gyro_dps = interp1(t_gyro, gyro_dps, t_acc, "linear", "extrap");
mag_G    = interp1(t_mag,  mag_G,    t_acc, "linear", "extrap");

% -------- convert units
gyro = deg2rad(gyro_dps);     % rad/s
acc  = acc_g * 9.80665;       % m/s^2
mag  = mag_G * 100;           % uT

% -------- sampling frequency
t_acc_s = fixTimeUnits(t_acc);
dt = median(diff(t_acc_s));
Fs = 1/dt;

% -------- filter settings (recommended)
AccLPHz  = 2;   % gravity extraction
MagLPHz  = 30;     % magnetometer smoothing
GyroLPHz = 30;    % remove high-frequency noise

% -------- store originals
acc_raw  = acc;
mag_raw  = mag;
gyro_raw = gyro;

% -------- Butterworth filter order
N = 2;

% -------- design filters
[b_acc,  a_acc]  = butter(N, AccLPHz/(Fs/2),  'low');
[b_mag,  a_mag]  = butter(N, MagLPHz/(Fs/2),  'low');
[b_gyro, a_gyro] = butter(N, GyroLPHz/(Fs/2), 'low');

% -------- apply zero-phase filtering
acc  = filtfilt(b_acc,  a_acc,  acc_raw);
mag  = filtfilt(b_mag,  a_mag,  mag_raw);
gyro = filtfilt(b_gyro, a_gyro, gyro_raw);


%% ================= PLOTS =================
if RawplotsOn

figure('Name','ACC Lowpass Comparison')
tiledlayout(3,1)
nexttile
plot(t_acc_s, acc_raw(:,1),'--'); hold on
plot(t_acc_s, acc(:,1),'LineWidth',1.2)
grid on; title('ACC X'); legend('Raw','Filtered')

nexttile
plot(t_acc_s, acc_raw(:,2),'--'); hold on
plot(t_acc_s, acc(:,2),'LineWidth',1.2)
grid on; title('ACC Y')

nexttile
plot(t_acc_s, acc_raw(:,3),'--'); hold on
plot(t_acc_s, acc(:,3),'LineWidth',1.2)
grid on; title('ACC Z'); xlabel('Time (s)')

figure('Name','GYRO Lowpass Comparison')
tiledlayout(3,1)
nexttile
plot(t_acc_s, gyro_raw(:,1),'--'); hold on
plot(t_acc_s, gyro(:,1),'LineWidth',1.2)
grid on; title('GYRO X'); legend('Raw','Filtered')

nexttile
plot(t_acc_s, gyro_raw(:,2),'--'); hold on
plot(t_acc_s, gyro(:,2),'LineWidth',1.2)
grid on; title('GYRO Y')

nexttile
plot(t_acc_s, gyro_raw(:,3),'--'); hold on
plot(t_acc_s, gyro(:,3),'LineWidth',1.2)
grid on; title('GYRO Z'); xlabel('Time (s)')

figure('Name','MAG Lowpass Comparison')
tiledlayout(3,1)
nexttile
plot(t_acc_s, mag_raw(:,1),'--'); hold on
plot(t_acc_s, mag(:,1),'LineWidth',1.2)
grid on; title('MAG X'); legend('Raw','Filtered')

nexttile
plot(t_acc_s, mag_raw(:,2),'--'); hold on
plot(t_acc_s, mag(:,2),'LineWidth',1.2)
grid on; title('MAG Y')

nexttile
plot(t_acc_s, mag_raw(:,3),'--'); hold on
plot(t_acc_s, mag(:,3),'LineWidth',1.2)
grid on; title('MAG Z'); xlabel('Time (s)')

end
gyro = [gyro(:,1) gyro(:,2)  gyro(:,3)];
acc  = -[acc(:,1) acc(:,2)  acc(:,3)];
mag  = [mag(:,1)  -mag(:,2)  mag(:,3)];

end

function t = fixTimeUnits(t)
dt = median(diff(t));
if dt > 0.5
    t = t * 1e-3;
end
end

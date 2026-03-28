addpath('quaternion_library');
clear; close all;


rideName = "dojebane";   

%% Base paths
rightBasePath = "C:\Users\risko\Desktop\CSV_Right"; 
leftBasePath  = "C:\Users\risko\Desktop\CSV_Left"; 
gpsBasePath   = "C:\Users\risko\Desktop\CSV_Left"; 
calbasePathL   = "C:\Users\risko\Desktop\Cal_left";
calbasePathR  = "C:\Users\risko\Desktop\Cal_right";


exportBaseFolder = "C:\Users\risko\Desktop\CSV_export"; 

%% Auto-generated paths
rightPath = fullfile(rightBasePath, rideName);
leftPath  = fullfile(leftBasePath,  rideName);
gpsPath   = fullfile(gpsBasePath,   rideName);
calpathL = fullfile(calbasePathL, rideName);
calpathR = fullfile(calbasePathR, rideName);

exportFolder = fullfile(exportBaseFolder, rideName);

if ~exist(exportFolder, 'dir')
    mkdir(exportFolder);
end

%% Flags
RawplotsOn = 0;

%% Time windows
magCalStart  = 0;
magCalStop   = 200;
gyroCalStart = 200;
gyroCalStop  = 220;
measStart    = 0;
measStop   = 4000; % tretia
% measStop     = 2500;

%% Gains
startupTime = 3;

Kp_fast = 1;
Ki_fast = 0;
MagWeight_fast = 1;
AccWeight_fast = 1;

Kp_run = 0.1;
Ki_run = 0;
MagWeight_run = 1;
AccWeight_run = 1;

%% Thresholds
accThreshold = 1;
magTolerance = 0;
biasSeconds = 50;

%% Filter
eulerLPHz = 1;
Nbutter = 2;

%% Config struct
cfg.RawplotsOn = RawplotsOn;
cfg.windows.magCalStart  = magCalStart;
cfg.windows.magCalStop   = magCalStop;
cfg.windows.gyroCalStart = gyroCalStart;
cfg.windows.gyroCalStop  = gyroCalStop;
cfg.windows.measStart    = measStart;
cfg.windows.measStop     = measStop;

cfg.startupTime = startupTime;

cfg.fast.Kp = Kp_fast;
cfg.fast.Ki = Ki_fast;
cfg.fast.MagWeight = MagWeight_fast;
cfg.fast.AccWeight = AccWeight_fast;

cfg.run.Kp = Kp_run;
cfg.run.Ki = Ki_run;
cfg.run.MagWeight = MagWeight_run;
cfg.run.AccWeight = AccWeight_run;

cfg.accThreshold = accThreshold;
cfg.magTolerance = magTolerance;
cfg.biasSeconds = biasSeconds;

cfg.eulerLPHz = eulerLPHz;
cfg.Nbutter = Nbutter;

cfg.stillGyroThresh = 2.0;        % deg/s
cfg.stillAccThresh = 0.15;        % m/s^2
cfg.stillBiasWindowSec = 1.0;     % s

%% Process
right = [];
left  = [];

if isfolder(rightPath) || isfile(rightPath)
    right = processDataAutoBiasCal(rightPath, calpathR, cfg);

else
    warning("Right path neexistuje: %s", rightPath);
end

if isfolder(leftPath) || isfile(leftPath)
    left  = processDataAutoBiasCal(leftPath,  calpathL, cfg);
else
    warning("Left path neexistuje: %s", leftPath);
end

% GPS - preferencne podla right timeline, inak left
if ~isempty(right)
    gps = processGPS(gpsPath, right.t);
elseif ~isempty(left)
    gps = processGPS(gpsPath, left.t);
else
    error("Ani right ani left data neboli nacitane, GPS sa neda prevzorkovat.");
end

rightStats = [];
leftStats  = [];

% Plot
if ~isempty(right) && ~isempty(left)
    plotBoth(right.euler, left.euler, left.t, right.t)
end

turnCfg = struct;

Turndetection = TurnDetectionIntervals(left, right, gps, turnCfg, false);
[tLeft, tRight] = peakZeroTimes(right.t, Turndetection, exportFolder);
StatsOverall  = StatsOverall(Turndetection, right, left, gps);

%% Export
if ~isempty(right)
    exportSkiCSV(right.t, right.euler, right.acc, right.gyro, right.mag, ...
        exportFolder, "right_ski");
end

if ~isempty(left)
    exportSkiCSV(left.t, left.euler, left.acc, left.gyro, left.mag, ...
        exportFolder, "left_ski");
end

exportGPSCSV(gps, exportFolder);
out = detailed(Turndetection, right, left, gps,tLeft,tRight,exportFolder);


R = estimateTurnRadiusFromGPS(gps, tLeft, tRight,exportFolder);


exportTurnDetection(Turndetection, exportFolder, 'turnDetection');

clc
% runPython

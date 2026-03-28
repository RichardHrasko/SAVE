addpath('quaternion_library');
clear; close all;

%% Root paths
measurementsRoot = "C:\Users\risko\Desktop\Measurements";
exportRoot = "C:\Users\risko\Desktop\export";

if ~exist(exportRoot, 'dir')
    mkdir(exportRoot);
end

%% Tags in file names
leftTag  = "JOR";   % zmen ak treba
rightTag = "YQR";   % zmen ak treba

%% Flags
RawplotsOn = 0;

%% Time windows
magCalStart  = 0;
magCalStop   = 180;
gyroCalStart = 140;
gyroCalStop  = 180;
measStart    = 180;
measStop     = inf;

%% Gains
startupTime = 3;

Kp_fast = 5;
Ki_fast = 0;
MagWeight_fast = 0.07;
AccWeight_fast = 1;

Kp_run = 0.5;
Ki_run = 0;
MagWeight_run = 0.05;
AccWeight_run = 1;

%% Thresholds
accThreshold = 1;
magTolerance = 0.05;
biasSeconds = 50;

%% Filter
eulerLPHz = 1;
Nbutter = 2;

%% Config struct
cfg = struct;
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

%% Najdi vsetky merania
D = dir(measurementsRoot);
D = D([D.isdir]);
D = D(~ismember({D.name}, {'.','..'}));

for k = 1:numel(D)

    measName = D(k).name;
    measFolder = fullfile(measurementsRoot, measName);

    exportFolder = fullfile(exportRoot, measName);
    if ~exist(exportFolder, 'dir')
        mkdir(exportFolder);
    end

    fprintf('\n==============================\n');
    fprintf('Spracovavam: %s\n', measName);
    fprintf('==============================\n');

    right = [];
    left  = [];
    gps   = [];

    tempRightFolder = "";
    tempLeftFolder  = "";

    try
        % vytvor docasne foldery len so subormi jednej lyze
        tempRightFolder = prepareTaggedFolder(measFolder, rightTag);
        tempLeftFolder  = prepareTaggedFolder(measFolder, leftTag);

        if strlength(tempRightFolder) == 0
            warning('Skipping %s - nenasli sa subory pre pravu lyzu (%s).', measName, rightTag);
            continue;
        end

        if strlength(tempLeftFolder) == 0
            warning('Skipping %s - nenasli sa subory pre lavu lyzu (%s).', measName, leftTag);
            continue;
        end

        right = processData(tempRightFolder, cfg);
        left  = processData(tempLeftFolder, cfg);

        if isempty(right) || ~isfield(right, 't') || isempty(right.t)
            warning('Skipping %s - right ski data missing or empty.', measName);
            continue;
        end

        if isempty(left) || ~isfield(left, 't') || isempty(left.t)
            warning('Skipping %s - left ski data missing or empty.', measName);
            continue;
        end

        % GPS: ak existuje podfolder gps, pouzi ten, inak cely priecinok merania
        gpsFolder = fullfile(measFolder, "gps");
        if isfolder(gpsFolder)
            gps = processGPS(gpsFolder, right.t);
        else
            gps = processGPS(measFolder, right.t);
        end

        if isempty(gps) || ~isfield(gps, 't') || isempty(gps.t)
            warning('Skipping %s - GPS data missing or empty.', measName);
            continue;
        end

        cfgTurn = struct;
        Turndetection = TurnDetectionIntervals(left, right, gps, cfgTurn, false);
        StatsOverall(Turndetection, right, left, gps);

        %% Export
        exportSkiCSV(right.t, right.euler, right.acc, right.gyro, right.mag, ...
            exportFolder, "right_ski");

        exportSkiCSV(left.t, left.euler, left.acc, left.gyro, left.mag, ...
            exportFolder, "left_ski");

        exportGPSCSV(gps, exportFolder);
        detailed(Turndetection, right, left, gps, exportFolder);
        exportTurnDetection(Turndetection, exportFolder, 'turnDetection');

        fprintf('Hotovo: %s\n', measName);

    catch ME
        warning('Chyba v merani %s: %s', measName, ME.message);
    end

    cleanupTempFolder(tempRightFolder);
    cleanupTempFolder(tempLeftFolder);
end

clc
runPython


function tempFolder = prepareTaggedFolder(measFolder, tag)

    tempFolder = "";

    allCsv = dir(fullfile(measFolder, "*.csv"));
    if isempty(allCsv)
        return;
    end

    names = string({allCsv.name});
    mask = contains(upper(names), upper(tag));

    taggedFiles = allCsv(mask);
    if isempty(taggedFiles)
        return;
    end

    tempFolder = fullfile(tempdir, "ski_import_tmp", char(java.util.UUID.randomUUID));
    if ~exist(tempFolder, 'dir')
        mkdir(tempFolder);
    end

    for i = 1:numel(taggedFiles)
        src = fullfile(taggedFiles(i).folder, taggedFiles(i).name);
        dst = fullfile(tempFolder, taggedFiles(i).name);
        copyfile(src, dst);
    end
end


function cleanupTempFolder(folderPath)
    if strlength(folderPath) == 0
        return;
    end

    if exist(folderPath, 'dir')
        try
            rmdir(folderPath, 's');
        catch
        end
    end
end
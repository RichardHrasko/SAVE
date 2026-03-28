function gps = loadGPS(folder)

gpsList = dir(fullfile(folder, "*.track"));
gpsFile = fullfile(folder, gpsList(1).name);

G = readmatrix(gpsFile, ...
    "FileType", "text", ...
    "Delimiter", ",", ...
    "NumHeaderLines", 2);

% columns:
% 1 time
% 2 latitude
% 3 longitude
% 4 altitude
% 5 accuracy
% 6 bearing
% 7 speed

gps = G(:,1:7);
gps(:,1) = (gps(:,1) - gps(1,1)) * 1e-3;   % time in seconds from 0

end
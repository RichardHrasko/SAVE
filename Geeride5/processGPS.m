function out = processGPS(folder, t_ref)

% -------- find file
gpsList = dir(fullfile(folder, "*.track"));
gpsFile = fullfile(folder, gpsList(1).name);

% -------- read
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

% -------- GPS time in seconds from start of GPS recording
t_gps = (gps(:,1) - gps(1,1))* 1e-3;

% -------- measurement window from reference time
t_start = t_ref(1);
t_stop  = t_ref(end);

% -------- keep only relevant GPS part
idx = (t_gps >= t_start) & (t_gps <= t_stop);

if ~any(idx)
    error("processGPS:NoOverlap", ...
        "GPS nema data v intervale %.3f az %.3f s.", t_start, t_stop);
end

gps_win = gps(idx,:);
t_gps_win = t_gps(idx);

% -------- resample to reference time
out.t = t_ref(:);

out.latitude  = interp1(t_gps_win, gps_win(:,2), out.t, "spline",  "extrap");
out.longitude = interp1(t_gps_win, gps_win(:,3), out.t, "spline",  "extrap");
out.altitude  = interp1(t_gps_win, gps_win(:,4), out.t, "spline",  "extrap");
out.accuracy  = interp1(t_gps_win, gps_win(:,5), out.t, "nearest", "extrap");
out.bearing   = interp1(t_gps_win, gps_win(:,6), out.t, "nearest", "extrap");
out.speed     = interp1(t_gps_win, gps_win(:,7), out.t, "spline",  "extrap");

% out.latitude  = interp1(t_gps_win, gps_win(:,2), out.t, "linear",  "extrap");
% out.longitude = interp1(t_gps_win, gps_win(:,3), out.t, "linear",  "extrap");
% out.altitude  = interp1(t_gps_win, gps_win(:,4), out.t, "linear",  "extrap");
% out.accuracy  = interp1(t_gps_win, gps_win(:,5), out.t, "nearest", "extrap");
% out.bearing   = interp1(t_gps_win, gps_win(:,6), out.t, "nearest", "extrap");
% out.speed     = interp1(t_gps_win, gps_win(:,7), out.t, "linear",  "extrap");

% out.t         = t_gps_win;
% out.latitude  = gps_win(:,2);
% out.longitude = gps_win(:,3);
% out.altitude  = gps_win(:,4);
% out.accuracy  = gps_win(:,5);
% out.bearing   = gps_win(:,6);
% out.speed     = gps_win(:,7);


out.data = [ ...
    out.t ...
    out.latitude ...
    out.longitude ...
    out.altitude ...
    out.accuracy ...
    out.bearing ...
    out.speed];

end
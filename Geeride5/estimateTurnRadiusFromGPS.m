function out = estimateTurnRadiusFromGPS(gps, tLeft, tRight, exportFolder)
% estimateTurnRadiusFromGPS
% Kombinacia:
%   1) fit kruznice cez body v intervale
%   2) radius z krivosti spline trajektorie
% a vrati jednu finalnu hodnotu radiusu pre kazdy obluk.
%
% INPUT:
%   gps         ... struct s poliami gps.t, gps.latitude, gps.longitude
%   tLeft       ... starty oblukov
%   tRight      ... konce oblukov
%   exportFolder... optional
%
% OUTPUT:
%   out.intervals
%   out.radiusCircle
%   out.radiusCurvature
%   out.radiusFinal
%   out.validCircle
%   out.validCurvature
%   out.validFinal

    if nargin < 3
        error('Treba zadat gps, tLeft, tRight.');
    end
    if nargin < 4
        exportFolder = [];
    end

    % --- GPS
    t   = gps.t(:);
    lat = gps.latitude(:);
    lon = gps.longitude(:);

    good = isfinite(t) & isfinite(lat) & isfinite(lon);
    t   = t(good);
    lat = lat(good);
    lon = lon(good);

    if numel(t) < 5
        error('Po odstraneni nevalidnych GPS bodov ostalo prilis malo dat.');
    end

    [t, idx] = sort(t);
    lat = lat(idx);
    lon = lon(idx);

    [t, iu] = unique(t, 'stable');
    lat = lat(iu);
    lon = lon(iu);

    if numel(t) < 5
        error('Po odstraneni duplicitnych casov ostalo prilis malo dat.');
    end

    % --- prevod na lokalne XY
    R_earth = 6371000;
    lat0 = lat(1);
    lon0 = lon(1);

    x = deg2rad(lon - lon0) .* R_earth .* cos(deg2rad(lat0));
    y = deg2rad(lat - lat0) .* R_earth;

    % --- spline cez cele data
    % poznamka: ak by fnder nefungoval, treba to prepisat na gradient verziu
    ppx   = spline(t, x);
    ppy   = spline(t, y);
    dppx  = fnder(ppx, 1);
    dppy  = fnder(ppy, 1);
    ddppx = fnder(ppx, 2);
    ddppy = fnder(ppy, 2);

    % --- intervaly
    intervals = [tLeft(:), tRight(:)];
    validIntervals = all(isfinite(intervals), 2) & intervals(:,2) > intervals(:,1);
    intervals = intervals(validIntervals, :);

    nInt = size(intervals,1);

    out = struct;
    out.intervals       = intervals;
    out.radiusCircle    = NaN(nInt,1);
    out.radiusCurvature = NaN(nInt,1);
    out.radiusFinal     = NaN(nInt,1);
    out.validCircle     = false(nInt,1);
    out.validCurvature  = false(nInt,1);
    out.validFinal      = false(nInt,1);
    out.numPoints       = zeros(nInt,1);

    for i = 1:nInt
        t1 = intervals(i,1);
        t2 = intervals(i,2);

        mask = t >= t1 & t <= t2;
        xi = x(mask);
        yi = y(mask);

        out.numPoints(i) = numel(xi);

        %% 1) circle fit
        if numel(xi) >= 5
            pts = unique([xi yi], 'rows', 'stable');
            xi2 = pts(:,1);
            yi2 = pts(:,2);

            if numel(xi2) >= 5
                A = [2*xi2, 2*yi2, ones(size(xi2))];
                b = xi2.^2 + yi2.^2;

                if rank(A) >= 3
                    p = A \ b;
                    xc = p(1);
                    yc = p(2);
                    c  = p(3);

                    Rc = sqrt(c + xc^2 + yc^2);

                    if isfinite(Rc) && isreal(Rc) && Rc > 0
                        out.radiusCircle(i) = Rc;
                        out.validCircle(i) = true;
                    end
                end
            end
        end

        %% 2) curvature zo spline
        tq = t(mask);
        if numel(tq) >= 5
            dx  = ppval(dppx, tq);
            dy  = ppval(dppy, tq);
            ddx = ppval(ddppx, tq);
            ddy = ppval(ddppy, tq);

            denom = (dx.^2 + dy.^2).^(3/2);
            numer = abs(dx .* ddy - dy .* ddx);

            kappa = NaN(size(tq));
            goodK = denom > 1e-9;
            kappa(goodK) = numer(goodK) ./ denom(goodK);

            kappa = kappa(isfinite(kappa) & kappa > 1e-9);

            if numel(kappa) >= 3
                % ekvivalentny radius z priemernej krivosti
                Rk = 1 / mean(kappa, 'omitnan');

                if isfinite(Rk) && isreal(Rk) && Rk > 0 && Rk < 1e4
                    out.radiusCurvature(i) = Rk;
                    out.validCurvature(i) = true;
                end
            end
        end

        %% 3) finalna kombinacia
        % identicky output format, ale bez zbytocneho disconnectu:
        % - ak su obe validne -> weighted average
        % - ak je validny len circle -> circle
        % - ak je validny len curvature -> curvature
        % - inak NaN
        if out.validCircle(i) && out.validCurvature(i)
            out.radiusFinal(i) = 0.7*out.radiusCircle(i) + 0.3*out.radiusCurvature(i);
            out.validFinal(i) = true;

        elseif out.validCircle(i)
            out.radiusFinal(i) = out.radiusCircle(i);
            out.validFinal(i) = true;

        elseif out.validCurvature(i)
            out.radiusFinal(i) = out.radiusCurvature(i);
            out.validFinal(i) = true;

        else
            out.radiusFinal(i) = NaN;
            out.validFinal(i) = false;
        end
    end

    % summary
    r = out.radiusFinal(out.validFinal);
    if isempty(r)
        out.avgTurnRadius = NaN;
        out.minTurnRadius = NaN;
        out.maxTurnRadius = NaN;
    else
        out.avgTurnRadius = mean(r, 'omitnan');
        out.minTurnRadius = min(r);
        out.maxTurnRadius = max(r);
    end

    % export
    if ~isempty(exportFolder)
        if ~exist(exportFolder, 'dir')
            mkdir(exportFolder);
        end

        T = table( ...
            out.intervals(:,1), ...
            out.intervals(:,2), ...
            out.radiusCircle, ...
            out.radiusCurvature, ...
            out.radiusFinal, ...
            out.validCircle, ...
            out.validCurvature, ...
            out.validFinal, ...
            out.numPoints, ...
            'VariableNames', { ...
                'tStart', ...
                'tStop', ...
                'radiusCircle_m', ...
                'radiusCurvature_m', ...
                'radiusFinal_m', ...
                'validCircle', ...
                'validCurvature', ...
                'validFinal', ...
                'numPoints'} );

        writetable(T, fullfile(exportFolder, 'turn_radius_combined.csv'));

        S = table( ...
            out.avgTurnRadius, ...
            out.minTurnRadius, ...
            out.maxTurnRadius, ...
            sum(out.validFinal), ...
            numel(out.validFinal), ...
            'VariableNames', { ...
                'avgTurnRadius_m', ...
                'minTurnRadius_m', ...
                'maxTurnRadius_m', ...
                'numValidTurns', ...
                'numIntervals'} );

        writetable(S, fullfile(exportFolder, 'turn_radius_combined_summary.csv'));
    end
end
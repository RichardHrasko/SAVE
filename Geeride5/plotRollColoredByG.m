function plotRollColoredByGStacked(tr, rightRoll, rightAcc, tl, leftRoll, leftAcc, figName)
% plotRollColoredByGStacked
% Two stacked roll plots, colored by g-level

if nargin < 7
    figName = 'Roll colored by g - stacked';
end

tr = tr(:);
tl = tl(:);
rightRoll = rightRoll(:);
leftRoll  = leftRoll(:);

if size(rightAcc,1) ~= length(tr)
    error('RightAcc and tr must have the same length.');
end

if size(leftAcc,1) ~= length(tl)
    error('LeftAcc and tl must have the same length.');
end

% Choose metric
gRight = vecnorm(rightAcc, 2, 2) / 9.80665;
gLeft  = vecnorm(leftAcc, 2, 2) / 9.80665;

% Shared color scale
allG = [gRight; gLeft];
gMin = prctile(allG, 5);
gMax = prctile(allG, 95);

if gMax <= gMin
    gMax = gMin + 1e-6;
end

figure('Name', figName, 'NumberTitle', 'off');
tiledlayout(2,1)

% ---------- RIGHT ----------
nexttile
hold on
grid on
title('Right ski roll')
ylabel('Roll (deg)')

gNorm = (gRight - gMin) / (gMax - gMin);
gNorm = max(0, min(1, gNorm));

for i = 1:length(tr)-1
    c = [1, 1-gNorm(i), 1-gNorm(i)];   % white -> red
    plot(tr(i:i+1), rightRoll(i:i+1), 'Color', c, 'LineWidth', 2);
end

% ---------- LEFT ----------
nexttile
hold on
grid on
title('Left ski roll')
xlabel('Time (s)')
ylabel('Roll (deg)')

gNorm = (gLeft - gMin) / (gMax - gMin);
gNorm = max(0, min(1, gNorm));

for i = 1:length(tl)-1
    c = [1, 1-gNorm(i), 1-gNorm(i)];
    plot(tl(i:i+1), leftRoll(i:i+1), 'Color', c, 'LineWidth', 2);
end

colormap([linspace(1,1,256)', linspace(1,0,256)', linspace(1,0,256)'])
cb = colorbar;
caxis([gMin gMax])
ylabel(cb, 'Acceleration magnitude (g)')

end
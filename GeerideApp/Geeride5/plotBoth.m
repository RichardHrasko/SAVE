function plotBoth(RightSki, LeftSki, tl, tr)

r = size(RightSki,1);
l = size(LeftSki,1);

n = min(r,l);

RightSki = RightSki(1:n,:);
LeftSki  = LeftSki(1:n,:);

% vyber čas tej kratšej alebo jednoducho orež obe časové osi
if length(tr) <= length(tl)
    t = tr(1:n);
else
    t = tl(1:n);
end

figure('Name','Filter','NumberTitle','off')
tiledlayout(3,1)

z = zeros(size(t));

% ROLL
nexttile
plot(t, (RightSki(:,1)), 'LineWidth', 1.2); hold on
plot(t, (LeftSki(:,1)),  'LineWidth', 1.2);
plot(t, z, 'LineWidth', 1.0)
grid on
ylabel('roll (deg)')
title('Estimated Orientation - ROLL')
legend('Right','Left','Zero')

% PITCH
nexttile
plot(t, (RightSki(:,2)), 'LineWidth', 1.2); hold on
plot(t, (LeftSki(:,2)),  'LineWidth', 1.2);
plot(t, z, 'LineWidth', 1.0)
grid on
ylabel('pitch (deg)')
title('Estimated Orientation - PITCH')
legend('Right','Left','Zero')

% YAW
nexttile
plot(t, (RightSki(:,3)), 'LineWidth', 1.2); hold on
plot(t, (LeftSki(:,3)),  'LineWidth', 1.2);
plot(t, z, 'LineWidth', 1.0)
grid on
ylabel('yaw (deg)')
xlabel('time (s)')
title('Estimated Orientation - YAW')
legend('Right','Left','Zero')

% Error plots
errRoll  = RightSki(:,1) - LeftSki(:,1);
errPitch = RightSki(:,2) - LeftSki(:,2);
errYaw   = RightSki(:,3) - LeftSki(:,3);

figure('Name','Errors','NumberTitle','off')
tiledlayout(3,1)

nexttile
plot(t, errRoll, 'LineWidth', 1.2); hold on
plot(t, z, 'LineWidth', 1.0)
grid on
ylabel('\Delta roll (deg)')
title('ROLL error (Right - Left)')
legend('Error','Zero')

nexttile
plot(t, errPitch, 'LineWidth', 1.2); hold on
plot(t, z, 'LineWidth', 1.0)
grid on
ylabel('\Delta pitch (deg)')
title('PITCH error (Right - Left)')
legend('Error','Zero')

nexttile
plot(t, errYaw, 'LineWidth', 1.2); hold on
plot(t, z, 'LineWidth', 1.0)
grid on
ylabel('\Delta yaw (deg)')
xlabel('time (s)')
title('YAW error (Right - Left)')
legend('Error','Zero')

rmseRoll  = sqrt(mean(errRoll.^2));
rmsePitch = sqrt(mean(errPitch.^2));
rmseYaw   = sqrt(mean(errYaw.^2));

disp(['RMSE roll  = ' num2str(rmseRoll,  '%.2f') ' deg'])
disp(['RMSE pitch = ' num2str(rmsePitch, '%.2f') ' deg'])
disp(['RMSE yaw   = ' num2str(rmseYaw,   '%.2f') ' deg'])

end
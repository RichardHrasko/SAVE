function [maxG, avgG, maxDynG, avgDynG] = computeG(acc)
    g0 = 9.80665;
    accMag = sqrt(sum(acc.^2,2));
    totalG = accMag / g0;
    dynG = abs(totalG - 1);

    maxG = max(totalG, [], 'omitnan');
    avgG = mean(totalG, 'omitnan');
    maxDynG = max(dynG, [], 'omitnan');
    avgDynG = mean(dynG, 'omitnan');
end
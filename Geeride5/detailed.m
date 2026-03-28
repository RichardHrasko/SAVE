function out = detailed(Turndetection, right, left, gps,tLeft,tRight,folder)

    out.overall = StatsOverall(Turndetection, right, left, gps, tLeft, tRight);
    exportOverallStatsCSV(out.overall, folder, 'overall_stats');

    nInt = size(Turndetection.intervals.t, 1);

    for i = 1:nInt
        t1 = Turndetection.intervals.t(i,1);
        t2 = Turndetection.intervals.t(i,2);
        

        maskR = right.t >= t1 & right.t <= t2;
        maskL = left.t  >= t1 & left.t  <= t2;
        maskG = gps.t   >= t1 & gps.t   <= t2;

        

        right_i.t = right.t(maskR);
        right_i.euler = right.euler(maskR,:);
        right_i.q = right.q(maskR);
        right_i.acc = right.acc(maskR,:);
        right_i.gyro = right.gyro(maskR,:);
        right_i.mag = right.mag(maskR,:);
        right_i.wAcc = right.wAcc(maskR);
        right_i.wMag = right.wMag(maskR);

        left_i.t = left.t(maskL);
        left_i.euler = left.euler(maskL,:);
        left_i.q = left.q(maskL);
        left_i.acc = left.acc(maskL,:);
        left_i.gyro = left.gyro(maskL,:);
        left_i.mag = left.mag(maskL,:);
        left_i.wAcc = left.wAcc(maskL);
        left_i.wMag = left.wMag(maskL);

        gps_i.t = gps.t(maskG);
        gps_i.latitude = gps.latitude(maskG);
        gps_i.longitude = gps.longitude(maskG);
        gps_i.altitude = gps.altitude(maskG);
        gps_i.accuracy = gps.accuracy(maskG);
        gps_i.bearing = gps.bearing(maskG);
        gps_i.speed = gps.speed(maskG);
        gps_i.data = gps.data(maskG,:);

        Turndetection_i = struct();

maskA = Turndetection.tPeaks >= t1 & Turndetection.tPeaks <= t2;
Turndetection_i.count   = sum(maskA);
Turndetection_i.tPeaks  = Turndetection.tPeaks(maskA);
Turndetection_i.idx     = Turndetection.idx(maskA);
Turndetection_i.values  = Turndetection.values(maskA);

maskL = Turndetection.peaks.left.tPeaks >= t1 & Turndetection.peaks.left.tPeaks <= t2;
Turndetection_i.peaks.left.tPeaks = Turndetection.peaks.left.tPeaks(maskL);
Turndetection_i.peaks.left.idx    = Turndetection.peaks.left.idx(maskL);
Turndetection_i.peaks.left.values = Turndetection.peaks.left.values(maskL);

maskR = Turndetection.peaks.right.tPeaks >= t1 & Turndetection.peaks.right.tPeaks <= t2;
Turndetection_i.peaks.right.tPeaks = Turndetection.peaks.right.tPeaks(maskR);
Turndetection_i.peaks.right.idx    = Turndetection.peaks.right.idx(maskR);
Turndetection_i.peaks.right.values = Turndetection.peaks.right.values(maskR);

maskAvg = Turndetection.peaks.avg.tPeaks >= t1 & Turndetection.peaks.avg.tPeaks <= t2;
Turndetection_i.peaks.avg.tPeaks = Turndetection.peaks.avg.tPeaks(maskAvg);
Turndetection_i.peaks.avg.idx    = Turndetection.peaks.avg.idx(maskAvg);
Turndetection_i.peaks.avg.values = Turndetection.peaks.avg.values(maskAvg);




Turndetection_i.intervals.t = [t1 t2];

        Turndetection_i.count = sum(Turndetection.tPeaks >= t1 & Turndetection.tPeaks <= t2);

        out.intervals(i).stats = StatsOverall(Turndetection_i, right_i, left_i, gps_i, tLeft, tRight);
        exportOverallStatsCSV(out.intervals(i).stats, folder, sprintf('interval_%02d_stats', i));
    end
end
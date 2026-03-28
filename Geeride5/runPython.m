function runPython 

pyExe = "C:\Users\risko\Desktop\GeerideApp\.venv\Scripts\python.exe";
pyScript = "C:\Users\risko\Desktop\GeerideApp\main.py";

cmd = sprintf('"%s" "%s"', pyExe, pyScript);
status = system(cmd);

if status ~= 0
    error('Python script failed.');
end

end
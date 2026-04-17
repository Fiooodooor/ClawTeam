
import os
import re
import pandas as pd


LOG_DO_COMPILE = 'log.do_compile'

flags = ['D_FORTIFY_SOURCE=2', 'relro', 'fstack-protector-strong', 'Wformat -Wformat-security''O1','O2','O3','PIE','fPIC']


log_files = []
f_with = []



for root, dirs, files in os.walk(r'/home/iblumshe/workspace_old/sources/ilil_build/tmp'):
    for file in files:
        if file.endswith(LOG_DO_COMPILE):
            log_files.append(os.path.join(root,file))

res = pd.DataFrame(columns=['log_file', 'compilation_file', 'flag'])
f_with.clear()
counter = 0
for file_path in log_files:
    with open(file_path,'r') as log_file:
        for line in log_file:
            for flag in flags:
                    if flag in line:
                        c_files=re.findall(("/[^/]+\.[co]"),line)
                        for f in c_files:
                            res.loc[counter] = [os.path.join(root, file_path), f, flag]
                            counter +=1
res.to_csv('out.csv')


import ts from 'typescript';
import { spawnSync } from 'node:child_process';
import { mkdir,readFile,writeFile } from 'node:fs/promises';
import path from 'node:path';
for(const file of ['lib/domain.ts','lib/seed.ts','tests/domain.test.ts']){
 const source=await readFile(file,'utf8');
 const output=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText.replace(/(from\s+['"])(\.{1,2}\/[^'"]+)(['"])/g,'$1$2.js$3');
 const target=path.join('.sites-runtime/tests',file.replace(/\.ts$/,'.js'));
 await mkdir(path.dirname(target),{recursive:true});await writeFile(target,output);
}
const result=spawnSync(process.execPath,['--test','.sites-runtime/tests/tests/domain.test.js'],{stdio:'inherit'});process.exit(result.status??1);

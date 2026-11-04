# Análisis estático — línea base (23/10/2026, antes de correcciones)

## ruff ruff 0.16.8
53	E702	[ ] multiple-statements-on-one-line-semicolon
26	E501	[ ] line-too-long
10	I001	[*] unsorted-imports
 5	E741	[ ] ambiguous-variable-name
 3	F401	[*] unused-import
 2	E401	[*] multiple-imports-on-one-line
 1	E731	[ ] lambda-assignment
 1	B007	[ ] unused-loop-control-variable
 1	F841	[ ] unused-variable
Found 102 errors.
[*] 15 fixable with the `--fix` option (3 hidden fixes can be enabled with the `--unsafe-fixes` option).

## bandit bandit 1.9.4

## ESLint (primera pasada)
2 errores: no-useless-escape en normalize.js:9; no-unused-vars 'sesionSha' en offscreen.js:7
## npm audit
0 vulnerabilidades

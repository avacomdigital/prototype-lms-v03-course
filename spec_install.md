# Feature Spec · Generar instalable 

### Objetivo

Crear un instalable cómo el instalable que está en dist dentro de la carpeta installer.


### Consideraciones de AVACOM OPS

La pantalla OPS no cuenta con un teclado, ni las personas que tienen acceso son programadores. Entonces debe ser un instalador muy completo:
- Puedes basarte en el instalador para lo que está en AVACOM OPS Master
- Debes crear el instalador para instalar también la API
- Considera que la API carga su SQLIte
- Debes inferir algunos valores del archivo .env
- Así mismo debe ser fácil de desinstalar
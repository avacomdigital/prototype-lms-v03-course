## Nuevo Requisito de ajustes

Se debe realizar un ajuste para eliminar y actualizar cuáles son los contenidos disponibles para los cursos del LMS

## Constitución del ajuste 
**Constitución** | `/speckit.constitution`

1. No se debe tratar de eliminar ninguna de las funcionalidades ya realizadas
2. Se requiere hacer una actualización constante en el endpoint de AVACOM Biblioteca con el objetivo de tener disponible el contenido de AVACOM Biblioteca en tiempo real en Panel del curso

#Especificación


Se realizó la siguiente prueba por medio de PowerShell que identifica los cursos disponibles:

PS C:\WINDOWS\system32> $n = Get-Content (Join-Path $env:ProgramData 'AVACOM\contenido\enlace.json') -Raw | ConvertFrom-Json
PS C:\WINDOWS\system32> $h = @{ 'X-Avacom-Ficha' = $n.Ficha }; $b = "http://127.0.0.1:$($n.Puerto)"
PS C:\WINDOWS\system32> (Invoke-RestMethod "$b/v1/catalogo" -Headers $h).elementos | Format-Table tipo, titulo, nivel, grado, asignatura, ref -AutoSize

tipo        titulo                           nivel      grado      asignatura            ref
----        ------                           -----      -----      ----------            ---
leccion     Los animales y dónde viven       preescolar transicion Exploración del medio co-pre-em-lec-animales
imagen      Lámina de la granja              preescolar transicion Exploración del medio co-pre-em-lam-granja
imagen      Lámina del bosque                preescolar transicion Exploración del medio co-pre-em-lam-bosque
video       Sonidos de los animales          preescolar transicion Exploración del medio co-pre-em-video-sonidos
actividad   ¿Dónde vive cada animal?         preescolar transicion Exploración del medio co-pre-em-act-donde-vive
evaluacion  Evaluación · Función lineal      secundaria 8          Matemáticas           co-sec-mat-eval-funcion
interactivo Explorador de rectas             secundaria 8          Matemáticas           co-sec-mat-int-grafica
leccion     Función lineal y razón de cambio secundaria 8          Matemáticas           co-sec-mat-lec-funcion
documento   La función lineal                secundaria 8          Matemáticas           co-sec-mat-doc-funcion
video       Qué significa la pendiente       secundaria 8          Matemáticas           co-sec-mat-video-pendiente


PS C:\WINDOWS\system32> (Invoke-RestMethod "$b/v1/catalogo" -Headers $h).elementos | Format-Table tipo, titulo, nivel, grado, asignatura, ref -AutoSize

tipo        titulo                           nivel      grado asignatura  ref
----        ------                           -----      ----- ----------  ---
evaluacion  Evaluación · Función lineal      secundaria 8     Matemáticas co-sec-mat-eval-funcion
interactivo Explorador de rectas             secundaria 8     Matemáticas co-sec-mat-int-grafica
leccion     Función lineal y razón de cambio secundaria 8     Matemáticas co-sec-mat-lec-funcion
documento   La función lineal                secundaria 8     Matemáticas co-sec-mat-doc-funcion
video       Qué significa la pendiente       secundaria 8     Matemáticas co-sec-mat-video-pendiente

Como se puede evidenciar en el segundo llamado a /v1/catalogo se eliminó el curso de "Exploración del medio", esto debe actualizarse en el AVACOM OPS Master y en su base de datos para comunicarlo más adelante a AVACOM Student.

Si el puerto cambia cada vez que arranca ¿Cómo hará el AVACOM OPS Master y su respectivo backend para saber dónde está ubicado? ¿Es decir en qué puerto apuntará?

Esa es exactamente la pregunta correcta, y el componente ya tiene la respuesta prevista: OPS Master nunca apunta a un puerto fijo, lo lee de una nota que el componente deja al arrancar.

El mecanismo
Al encender la API, el componente escribe:

%ProgramData%\AVACOM\contenido\enlace.json
{"Contrato":1,"Puerto":57495,"Ficha":"3681b210...","Proceso":43700}
Y al cerrarse bien, la borra. Los cuatro campos, y para qué sirve cada uno:

Campo	Para qué
Contrato	Versión del contrato. Comprobarla y negarse a hablar si no es un número que el backend entienda
Puerto	A dónde llamar. Siempre 127.0.0.1
Ficha	Va en X-Avacom-Ficha en cada petición. Sin ella, 401
Proceso	PID, para comprobar que sigue vivo
Por qué puerto efímero y no uno fijo: un puerto conocido es un punto que sondear, y además choca cuando dos cosas quieren el mismo número. La nota resuelve el problema sin fijar nada.

## Tareas

Las tareas a realizar son las siguientes:

1. Verificar que se esté llamando correctamente a  /v1/catalogo comprendiendo que puede variar de puerto
2. Realizar una función, clase o objeto que permita llamar al endpoint y sea reutilizable en todo el código de AVACOM OPS Master
3. Consolidar que cada vez que se abra la ventana de resumen se haga un refresco y limpie los cursos que ya no existen según   /v1/catalogo porque han sido eliminados
4. El refresco y limpieza también podría ejecutarse en el botón de "Actualizar" que se encuentra dentro de resumen
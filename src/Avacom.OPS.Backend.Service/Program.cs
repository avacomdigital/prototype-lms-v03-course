using Avacom.OPS.Backend.Service;
using Microsoft.Extensions.Hosting.WindowsServices;

// ─────────────────────────────────────────────────────────────────────────────
// AVACOMOPSBackend · el servicio de Windows que mantiene viva la API del aula
//
// Existe por una razón concreta: hasta ahora la API la levantaba el panel del
// profesor, así que las tabletas solo tenían servicio mientras alguien tuviera
// abierta la aplicación. Un aula no funciona así. Con este servicio la API
// escucha desde que arranca Windows, y el panel es un cliente más.
//
// Lo que hace es deliberadamente poco: lanza el mismo daphne que ya se usaba,
// con el mismo Python embebido y los mismos argumentos, y lo vigila. NO
// reimplementa nada del backend ni cambia cómo se sirve.
//
// SOBRE WAITRESS. La especificación sugiere Waitress. No se usa, y el motivo es
// que este backend sirve WebSockets: Channels, ASGI_APPLICATION y la ruta
// ws/activities/{id}/ que el panel abre como profesor para seguir un examen en
// vivo. Waitress es WSGI y no puede atender un WebSocket, así que cambiarlo
// rompería el canal en tiempo real. daphne ya cumple lo que el requisito busca
// —un servidor de producción en 0.0.0.0:8000, no `manage.py runserver`— y
// además es el que ya está probado. Si algún día el proyecto deja de usar
// WebSockets, Waitress vuelve a ser una opción razonable.
//
// Se ejecuta también desde consola (sin instalar el servicio) para poder
// diagnosticar: `Avacom.OPS.Backend.Service.exe --consola`.
// ─────────────────────────────────────────────────────────────────────────────

var enConsola = args.Contains("--consola", StringComparer.OrdinalIgnoreCase)
                || args.Contains("--console", StringComparer.OrdinalIgnoreCase);

if (enConsola)
{
    // La consola de Windows usa una pagina de codigos OEM, asi que los acentos
    // de los mensajes salen roto al diagnosticar. En el registro de eventos no
    // ocurre, pero el modo consola existe precisamente para leerlo, y un
    // diagnostico ilegible no diagnostica.
    try { Console.OutputEncoding = System.Text.Encoding.UTF8; }
    catch (Exception) { /* consola redirigida a algo que no lo admite */ }
}

var builder = Host.CreateApplicationBuilder(args);
builder.Services.AddHostedService<BackendWorker>();

if (!enConsola && WindowsServiceHelpers.IsWindowsService())
{
    builder.Services.AddWindowsService(opciones => opciones.ServiceName = "AVACOMOPSBackend");
}

var host = builder.Build();
await host.RunAsync();

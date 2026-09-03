using Avacom.OPS.Core.Models;

namespace Avacom.OPS.Core.Services;

/// <summary>
/// La única puerta del OPS Master hacia la biblioteca del aula.
///
/// Existe para que ninguna pantalla tenga que saber tres cosas que no le
/// importan: que el componente vive en un puerto que cambia en cada arranque,
/// que hay que leer <c>%ProgramData%\AVACOM\contenido\enlace.json</c> para
/// encontrarlo, y que la ficha va en <c>X-Avacom-Ficha</c>. Nada de eso ocurre
/// aquí tampoco: ocurre en el BACKEND, que es el único cliente del componente.
/// Esta clase habla con el backend.
///
/// <para>
/// Por qué el puerto no se fija nunca. Un puerto conocido es un punto que
/// sondear y además choca cuando dos procesos quieren el mismo número. La nota
/// que el componente deja al arrancar resuelve las dos cosas, y el backend la
/// vuelve a leer EN CADA petición: guardarla en memoria es la forma segura de
/// seguir llamando a un puerto que ya murió. Por eso reiniciar la biblioteca no
/// obliga a reiniciar nada de este lado.
/// </para>
///
/// <para>
/// Quien necesite catálogo, estado o reconciliación pide por aquí. Si aparece
/// otra pantalla del Master llamando a <c>api/contenido/...</c> por su cuenta,
/// está mal: el manejo de «no hay biblioteca», la detección de cambios y el
/// mensaje que ve el docente se escriben una sola vez.
/// </para>
/// </summary>
public sealed class BibliotecaDeContenido(ILmsApiClient api)
{
    private string _huella = "";

    /// <summary>Lo último que se supo de la biblioteca. Null hasta la primera consulta.</summary>
    public ContenidoEstado? Estado { get; private set; }

    /// <summary>Si hay biblioteca con la que hablar ahora mismo.</summary>
    public bool Disponible => Estado?.Available == true;

    /// <summary>
    /// Consulta el estado y dice si el catálogo cambió desde la última vez.
    ///
    /// La comparación es contra la huella que publica el backend —<c>generacion</c>
    /// cuando el componente la publique, y los contadores mientras no—. Es una
    /// respuesta diminuta, así que se puede preguntar a menudo; traer el catálogo
    /// entero para comparar sería caro y haría parpadear las listas.
    /// </summary>
    public async Task<(ContenidoEstado estado, bool cambio)> ConsultarEstadoAsync(
        CancellationToken cancellationToken = default)
    {
        var estado = await api.GetContenidoEstadoAsync(cancellationToken);
        var huella = $"{estado.Available}:{estado.CatalogFingerprint}";
        var cambio = huella != _huella;
        _huella = huella;
        Estado = estado;
        return (estado, cambio);
    }

    /// <summary>
    /// El catálogo de ahora, ya filtrado por la política de la escuela.
    ///
    /// Devuelve la lista vacía cuando no hay biblioteca, en vez de lanzar: una
    /// pantalla del panel no puede quedarse en blanco porque el docente cerró la
    /// aplicación de contenido. El motivo queda en <see cref="Estado"/>.
    /// </summary>
    public async Task<IReadOnlyList<ContenidoElemento>> CatalogoAsync(
        string? tipo = null, string? nivel = null, string? grado = null,
        string? asignatura = null, CancellationToken cancellationToken = default)
    {
        try
        {
            var catalogo = await api.GetContenidoCatalogoAsync(
                nivel, grado, asignatura, tipo, cancellationToken);
            return catalogo.Elements;
        }
        catch (LmsApiException excepcion) when (excepcion.StatusCode == 503)
        {
            // 503 es «la biblioteca no está», que es una situación normal en un
            // aula. No es un fallo del que haya que avisar con una excepción.
            return [];
        }
    }

    /// <summary>
    /// Pone al día lo que el LMS cree disponible con lo que la biblioteca ofrece.
    ///
    /// Es idempotente, así que se puede colgar de la apertura de una pantalla y
    /// del botón «Actualizar» sin contar cuántas veces se dispara. Marca lo que
    /// desapareció, lo que volvió, y retira de las tabletas lo que el equipo ya
    /// no puede servir. NO borra referencias, matrículas, progreso ni notas.
    /// </summary>
    public async Task<ReconciliacionResultado?> ReconciliarAsync(
        string hostId, CancellationToken cancellationToken = default)
    {
        try
        {
            return await api.ReconciliarContenidoAsync(hostId, cancellationToken);
        }
        catch (LmsApiException excepcion) when (excepcion.StatusCode == 503)
        {
            // Sin biblioteca no se reconcilia, y eso es lo correcto: comparar
            // contra un catálogo que no se pudo leer marcaría todo como
            // desaparecido justo cuando menos conviene.
            return null;
        }
    }

    /// <summary>
    /// Si el contenido de un curso sigue en el equipo.
    ///
    /// Devuelve null cuando no hay con qué comprobarlo, y eso NO es lo mismo que
    /// «está retirado»: la pantalla debe decir «no se pudo comprobar», porque
    /// afirmar que el contenido desapareció cuando solo está cerrada la
    /// biblioteca es peor que no decir nada.
    /// </summary>
    public async Task<CursoContenido?> ContenidoDelCursoAsync(
        string courseId, CancellationToken cancellationToken = default)
    {
        try
        {
            return await api.GetCursoContenidoAsync(courseId, cancellationToken);
        }
        catch (LmsApiException excepcion) when (excepcion.StatusCode == 503)
        {
            return null;
        }
    }

    /// <summary>Qué material de la biblioteca tiene cada curso, y cuánto falta.</summary>
    public async Task<IReadOnlyList<CursoConMaterial>> PorCursoAsync(
        CancellationToken cancellationToken = default)
    {
        try
        {
            var informe = await api.GetInformeContenidoAsync(cancellationToken);
            Estado = informe.Component;
            return informe.ByCourse;
        }
        catch (LmsApiException excepcion) when (excepcion.StatusCode == 503)
        {
            return [];
        }
    }

    /// <summary>
    /// Olvida la huella para que la próxima consulta cuente como cambio.
    ///
    /// Sirve al entrar a una pantalla: se quiere recargar aunque el catálogo no
    /// haya cambiado desde la última vez que alguien miró.
    /// </summary>
    public void OlvidarHuella() => _huella = "";
}

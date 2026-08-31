namespace Avacom.OPS.Master.Services;

/// <summary>Qué clase de paquete eligió el docente.</summary>
public enum PackageKind
{
    /// <summary>avacom-course-package/v1 · un .json</summary>
    Native,
    /// <summary>SCORM 1.2 / 2004 o CMI5 · un .zip con su descriptor dentro</summary>
    Zip,
}

/// <summary>
/// El archivo que el docente eligió.
///
/// Se guardan los BYTES y no solo el texto: un .zip es binario, y además el
/// backend calcula la huella SHA-256 sobre el archivo tal como llegó. Convertirlo
/// a string y de vuelta la alteraría, y entonces reinstalar el mismo paquete no
/// se reconocería como el mismo.
/// </summary>
public sealed record PackageFile(string Name, byte[] Content, PackageKind Kind)
{
    public long Bytes => Content.LongLength;

    /// <summary>Solo para el formato nativo: el .json como texto.</summary>
    public string AsJson() => Kind == PackageKind.Native
        ? System.Text.Encoding.UTF8.GetString(Content)
        : throw new InvalidOperationException(
            "Este paquete es un .zip; usa Content y los endpoints de SCORM/CMI5.");

    public string KindLabel => Kind == PackageKind.Zip ? "SCORM / CMI5" : "Paquete AVACOM";

    public string SizeLabel => Bytes >= 1024 * 1024
        ? $"{Bytes / 1024d / 1024d:0.0} MB"
        : $"{Bytes / 1024d:0.0} KB";
}

/// <summary>
/// Abrir un archivo es una capacidad de la plataforma, no una regla del negocio.
/// Detrás de esta interfaz el ViewModel no sabe de FilePicker ni de rutas, y en
/// una prueba se sustituye por una que devuelve un paquete fijo.
/// </summary>
public interface IPackageFileSource
{
    Task<PackageFile?> PickAsync(CancellationToken cancellationToken = default);
}

public sealed class MauiPackageFileSource : IPackageFileSource
{
    // La OPS es una pantalla táctil sin teclado: el diálogo del sistema es la
    // única vía razonable para elegir un archivo. Se aceptan las dos familias en
    // un solo filtro para que el docente no tenga que decidir antes de abrir:
    //   .zip   SCORM 1.2 / SCORM 2004 / CMI5   (el formato se detecta del descriptor)
    //   .json  el paquete nativo de AVACOM
    private static readonly FilePickerFileType TiposDePaquete = new(
        new Dictionary<DevicePlatform, IEnumerable<string>>
        {
            [DevicePlatform.WinUI] = [".zip", ".json"],
            [DevicePlatform.Android] = ["application/zip", "application/json"],
        });

    public async Task<PackageFile?> PickAsync(CancellationToken cancellationToken = default)
    {
        var result = await FilePicker.Default.PickAsync(new PickOptions
        {
            PickerTitle = "Elige el paquete del curso (.zip SCORM/CMI5 o .json)",
            FileTypes = TiposDePaquete,
        });

        if (result is null) return null;

        await using var stream = await result.OpenReadAsync();
        using var buffer = new MemoryStream();
        await stream.CopyToAsync(buffer, cancellationToken);
        var contenido = buffer.ToArray();

        // La extensión decide a qué endpoint va; el ESTÁNDAR concreto (1.2, 2004
        // o CMI5) lo detecta el backend leyendo el descriptor del .zip, que es el
        // único lugar donde esa información es fiable.
        var kind = result.FileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase)
            ? PackageKind.Native
            : PackageKind.Zip;

        return new PackageFile(result.FileName, contenido, kind);
    }
}

namespace Avacom.OPS.Master.Services;

/// <summary>El archivo que el docente eligió: su nombre y su contenido, nada más.</summary>
public sealed record PackageFile(string Name, string Json, long Bytes);

/// <summary>
/// Abrir un archivo es una capacidad de la plataforma, no una regla del negocio.
/// Detrás de esta interfaz el ViewModel no sabe de FilePicker ni de rutas, y en
/// una prueba se sustituye por una que devuelve un JSON fijo.
/// </summary>
public interface IPackageFileSource
{
    Task<PackageFile?> PickAsync(CancellationToken cancellationToken = default);
}

public sealed class MauiPackageFileSource : IPackageFileSource
{
    // La OPS es una pantalla táctil sin teclado: el diálogo del sistema es la
    // única vía razonable para elegir un archivo, y el filtro evita que el
    // docente tenga que distinguir extensiones.
    private static readonly FilePickerFileType JsonType = new(
        new Dictionary<DevicePlatform, IEnumerable<string>>
        {
            [DevicePlatform.WinUI] = [".json"],
            [DevicePlatform.Android] = ["application/json"],
        });

    public async Task<PackageFile?> PickAsync(CancellationToken cancellationToken = default)
    {
        var result = await FilePicker.Default.PickAsync(new PickOptions
        {
            PickerTitle = "Elige el paquete del curso (.json)",
            FileTypes = JsonType,
        });

        if (result is null) return null;

        await using var stream = await result.OpenReadAsync();
        using var reader = new StreamReader(stream);
        var json = await reader.ReadToEndAsync(cancellationToken);
        return new PackageFile(result.FileName, json, json.Length);
    }
}

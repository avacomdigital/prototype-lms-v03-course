namespace Avacom.OPS.Core.Services;

public interface ILocalLog
{
    Task WriteAsync(string category, string message, Exception? exception = null);
}

public sealed class FileLocalLog(string filePath) : ILocalLog
{
    private readonly SemaphoreSlim _gate = new(1, 1);

    public async Task WriteAsync(string category, string message, Exception? exception = null)
    {
        var line = $"{DateTimeOffset.Now:O} [{category}] {message}{(exception is null ? "" : $" | {exception}")}{Environment.NewLine}";
        await _gate.WaitAsync();
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(filePath)!);
            await File.AppendAllTextAsync(filePath, line);
        }
        finally { _gate.Release(); }
    }
}


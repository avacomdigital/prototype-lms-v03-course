using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Avacom.OPS.Core.Models;

namespace Avacom.OPS.Core.Services;

public interface ILmsRealtimeClient : IAsyncDisposable
{
    event EventHandler<LmsRealtimeEvent>? EventReceived;
    event EventHandler<bool>? ConnectionChanged;
    Task RunAsync(Uri uri, CancellationToken cancellationToken);
}

public sealed class LmsRealtimeClient : ILmsRealtimeClient
{
    private readonly JsonSerializerOptions _json = new(JsonSerializerDefaults.Web);
    private ClientWebSocket? _socket;

    public event EventHandler<LmsRealtimeEvent>? EventReceived;
    public event EventHandler<bool>? ConnectionChanged;

    public async Task RunAsync(Uri uri, CancellationToken cancellationToken)
    {
        var attempt = 0;
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                _socket?.Dispose();
                _socket = new ClientWebSocket();
                _socket.Options.KeepAliveInterval = TimeSpan.FromSeconds(15);
                var originScheme = uri.Scheme == "wss" ? "https" : "http";
                _socket.Options.SetRequestHeader("Origin", $"{originScheme}://{uri.Authority}");
                await _socket.ConnectAsync(uri, cancellationToken);
                attempt = 0;
                ConnectionChanged?.Invoke(this, true);
                await ReceiveLoopAsync(_socket, cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { break; }
            catch (Exception) when (!cancellationToken.IsCancellationRequested)
            {
                ConnectionChanged?.Invoke(this, false);
            }

            if (cancellationToken.IsCancellationRequested) break;
            var delay = TimeSpan.FromSeconds(Math.Min(20, Math.Pow(2, Math.Min(++attempt, 4))));
            try { await Task.Delay(delay, cancellationToken); }
            catch (OperationCanceledException) { break; }
        }
    }

    private async Task ReceiveLoopAsync(ClientWebSocket socket, CancellationToken cancellationToken)
    {
        var buffer = new byte[8192];
        while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
        {
            using var stream = new MemoryStream();
            WebSocketReceiveResult result;
            do
            {
                result = await socket.ReceiveAsync(buffer, cancellationToken);
                if (result.MessageType == WebSocketMessageType.Close) return;
                stream.Write(buffer, 0, result.Count);
            } while (!result.EndOfMessage);

            if (result.MessageType != WebSocketMessageType.Text) continue;
            var message = JsonSerializer.Deserialize<LmsRealtimeEvent>(Encoding.UTF8.GetString(stream.ToArray()), _json);
            if (message is not null) EventReceived?.Invoke(this, message);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_socket?.State == WebSocketState.Open)
        {
            try { await _socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Cierre", CancellationToken.None); }
            catch (WebSocketException) { }
        }
        _socket?.Dispose();
    }
}

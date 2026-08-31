using System.Net;

namespace Avacom.OPS.Core.Tests;

public sealed class StubHttpHandler(Func<HttpRequestMessage, HttpResponseMessage> responder) : HttpMessageHandler
{
    public List<HttpRequestMessage> Requests { get; } = [];

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var copy = new HttpRequestMessage(request.Method, request.RequestUri);
        if (request.Content is not null)
            copy.Content = new StringContent(await request.Content.ReadAsStringAsync(cancellationToken));
        Requests.Add(copy);
        var response = responder(request);
        response.RequestMessage = request;
        return response;
    }

    public static HttpResponseMessage Json(string json, HttpStatusCode status = HttpStatusCode.OK) =>
        new(status) { Content = new StringContent(json, System.Text.Encoding.UTF8, "application/json") };
}

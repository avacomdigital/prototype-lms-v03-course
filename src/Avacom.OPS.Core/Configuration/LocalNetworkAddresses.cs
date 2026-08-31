using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace Avacom.OPS.Core.Configuration;

/// <summary>Una dirección IPv4 de este equipo, con el nombre de la interfaz que la expone.</summary>
public sealed record LocalNetworkAddress(string Address, string InterfaceName);

/// <summary>
/// Datos crudos de una interfaz, tal como los entrega el sistema operativo. Existe para
/// poder ordenar candidatas sin hardware de por medio: <see cref="LocalNetworkAddresses.Rank"/>
/// es una función pura y sí se puede probar, mientras que <see cref="LocalNetworkAddresses.Discover"/>
/// depende de las tarjetas de red del equipo donde corra.
/// </summary>
public sealed record NetworkCandidate(
    string Address,
    string InterfaceName,
    string Description,
    NetworkInterfaceType Type,
    bool HasGateway);

/// <summary>
/// Descubre con qué dirección alcanzan las tabletas a este equipo.
/// </summary>
/// <remarks>
/// El profesor necesita dictar una dirección y que funcione a la primera. El problema es
/// que un portátil de trabajo casi nunca tiene una sola IPv4: entre WSL, Docker, Hyper-V
/// y las VPN aparecen media docena, y las virtuales no son alcanzables desde la Wi-Fi de
/// la sede. Elegir la primera de la lista es exactamente el error que hace perder media
/// hora al inicio de un examen.
/// </remarks>
public static class LocalNetworkAddresses
{
    /// <summary>
    /// Fragmentos que delatan un adaptador virtual. Se comparan contra el nombre y la
    /// descripción porque, según el fabricante, el indicio aparece en uno o en el otro.
    /// </summary>
    private static readonly string[] VirtualHints =
        ["virtual", "vethernet", "wsl", "hyper-v", "vmware", "virtualbox", "docker", "loopback", "tap-", "tunnel", "bluetooth"];

    /// <summary>
    /// Direcciones IPv4 de este equipo, de la más probable a la menos. La primera es la
    /// que hay que mostrar; el resto se ofrecen por si la sede tiene una red inusual.
    /// </summary>
    public static IReadOnlyList<LocalNetworkAddress> Discover()
    {
        var candidates = new List<NetworkCandidate>();

        foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (nic.OperationalStatus != OperationalStatus.Up) continue;
            if (nic.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;

            IPInterfaceProperties properties;
            // Una interfaz puede desaparecer entre la enumeración y la consulta, por
            // ejemplo al desconectar un adaptador USB. No debe tumbar el descubrimiento.
            try { properties = nic.GetIPProperties(); }
            catch (NetworkInformationException) { continue; }

            var hasGateway = properties.GatewayAddresses.Any(g => g.Address is { AddressFamily: AddressFamily.InterNetwork } address
                                                                  && !address.Equals(IPAddress.Any));

            foreach (var info in properties.UnicastAddresses)
            {
                if (info.Address.AddressFamily != AddressFamily.InterNetwork) continue;
                if (IPAddress.IsLoopback(info.Address)) continue;
                candidates.Add(new NetworkCandidate(info.Address.ToString(), nic.Name, nic.Description, nic.NetworkInterfaceType, hasGateway));
            }
        }

        return Rank(candidates);
    }

    /// <summary>
    /// Ordena las candidatas por probabilidad de ser alcanzable desde otra máquina de la
    /// misma red, y descarta las que con certeza no lo son.
    /// </summary>
    public static IReadOnlyList<LocalNetworkAddress> Rank(IEnumerable<NetworkCandidate> candidates) =>
        candidates
            .Where(candidate => !IsAutoConfigured(candidate.Address))
            .OrderByDescending(Score)
            .ThenBy(candidate => candidate.Address, StringComparer.Ordinal)
            .Select(candidate => new LocalNetworkAddress(candidate.Address, candidate.InterfaceName))
            .ToList();

    private static int Score(NetworkCandidate candidate)
    {
        var score = 0;

        // Tener puerta de enlace es la señal más fiable de que la interfaz está en una
        // red de verdad y no en un puente interno de virtualización.
        if (candidate.HasGateway) score += 100;

        if (candidate.Type is NetworkInterfaceType.Wireless80211 or NetworkInterfaceType.Ethernet) score += 40;

        if (IsVirtual(candidate)) score -= 200;

        return score;
    }

    private static bool IsVirtual(NetworkCandidate candidate) =>
        VirtualHints.Any(hint =>
            candidate.InterfaceName.Contains(hint, StringComparison.OrdinalIgnoreCase) ||
            candidate.Description.Contains(hint, StringComparison.OrdinalIgnoreCase));

    /// <summary>
    /// 169.254.x.x es la dirección que Windows se asigna cuando el DHCP no respondió.
    /// Nunca sirve para que otro equipo se conecte, así que se descarta en lugar de
    /// ordenarse al final: mostrarla sólo produce intentos fallidos.
    /// </summary>
    private static bool IsAutoConfigured(string address) => address.StartsWith("169.254.", StringComparison.Ordinal);
}

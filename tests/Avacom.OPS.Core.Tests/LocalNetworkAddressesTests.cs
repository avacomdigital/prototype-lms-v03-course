using System.Net.NetworkInformation;
using Avacom.OPS.Core.Configuration;

namespace Avacom.OPS.Core.Tests;

/// <summary>
/// La dirección que el profesor dicta a la clase sale de aquí. Si el orden es incorrecto
/// se dicta una IP de WSL o de Docker, las tabletas no conectan y el fallo parece de red.
/// </summary>
public sealed class LocalNetworkAddressesTests
{
    private static NetworkCandidate Candidate(
        string address,
        string name = "Wi-Fi",
        string description = "Intel Wireless-AC",
        NetworkInterfaceType type = NetworkInterfaceType.Wireless80211,
        bool hasGateway = true) =>
        new(address, name, description, type, hasGateway);

    [Fact]
    public void La_interfaz_con_puerta_de_enlace_va_primero()
    {
        var ranked = LocalNetworkAddresses.Rank([
            Candidate("172.28.144.1", "vEthernet (WSL)", "Hyper-V Virtual Ethernet Adapter", NetworkInterfaceType.Ethernet, hasGateway: false),
            Candidate("192.168.0.27"),
        ]);

        Assert.Equal("192.168.0.27", ranked[0].Address);
    }

    [Fact]
    public void Los_adaptadores_virtuales_quedan_detras_aunque_tengan_puerta_de_enlace()
    {
        var ranked = LocalNetworkAddresses.Rank([
            Candidate("192.168.56.1", "VirtualBox Host-Only Network", "VirtualBox Host-Only Ethernet Adapter", NetworkInterfaceType.Ethernet),
            Candidate("10.0.0.15", "Ethernet", "Realtek Gaming GbE", NetworkInterfaceType.Ethernet),
        ]);

        Assert.Equal("10.0.0.15", ranked[0].Address);
        Assert.Equal("192.168.56.1", ranked[1].Address);
    }

    [Fact]
    public void Se_descarta_la_direccion_de_autoconfiguracion()
    {
        // 169.254.x.x es lo que Windows se asigna cuando el DHCP no respondió: nunca
        // sirve para que una tableta conecte, así que no debe ni ofrecerse.
        var ranked = LocalNetworkAddresses.Rank([
            Candidate("169.254.10.3", hasGateway: false),
            Candidate("192.168.0.27"),
        ]);

        Assert.Equal(["192.168.0.27"], ranked.Select(address => address.Address));
    }

    [Fact]
    public void Sin_ninguna_candidata_devuelve_una_lista_vacia_y_no_lanza()
    {
        Assert.Empty(LocalNetworkAddresses.Rank([]));
    }

    [Fact]
    public void Conserva_el_nombre_de_la_interfaz_para_poder_mostrarlo()
    {
        var ranked = LocalNetworkAddresses.Rank([Candidate("192.168.0.27", name: "Wi-Fi 6")]);

        Assert.Equal("Wi-Fi 6", ranked[0].InterfaceName);
    }

    [Fact]
    public void El_orden_es_estable_entre_candidatas_equivalentes()
    {
        // Sin desempate, dos tarjetas idénticas alternarían el orden entre sondeos y la
        // dirección mostrada cambiaría sola delante del profesor.
        var primero = LocalNetworkAddresses.Rank([Candidate("192.168.0.99"), Candidate("192.168.0.27")]);
        var segundo = LocalNetworkAddresses.Rank([Candidate("192.168.0.27"), Candidate("192.168.0.99")]);

        Assert.Equal(primero.Select(a => a.Address), segundo.Select(a => a.Address));
    }
}

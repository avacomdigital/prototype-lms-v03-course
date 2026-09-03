using Avacom.OPS.Core.Models;

namespace Avacom.Student.Services;

/// <summary>
/// Lo que la tableta sabe del alumno y del aula durante la sesión.
///
/// Vive en memoria a propósito: no hay login, así que no hay nada que persistir
/// más allá de la dirección del nodo, que sí se guarda en las preferencias
/// porque no cambia entre días.
/// </summary>
public sealed class ExamSession
{
    public string StudentName { get; set; } = "";

    /// <summary>
    /// Con qué identificador el backend guarda su progreso. Sale del nombre,
    /// porque sin login es lo único que hay; escribir el mismo nombre recupera
    /// el mismo avance.
    /// </summary>
    public string PersonId { get; set; } = "";

    public string ServerAddress { get; set; } = "";

    /// <summary>
    /// El equipo del aula. Se descubre al conectar, leyendo la API: el nombre de
    /// la máquina no se deduce de una dirección IP, y no se le puede pedir a un
    /// alumno de transición.
    /// </summary>
    public string HostId { get; set; } = "";

    /// <summary>
    /// Lo mantiene el guardián de pantalla completa de cada plataforma. Sin
    /// exámenes en la tableta hoy queda siempre en false, pero los servicios de
    /// kiosco lo consultan y quitarlo obligaría a tocarlos.
    /// </summary>
    public bool IsExamInProgress { get; set; }
}

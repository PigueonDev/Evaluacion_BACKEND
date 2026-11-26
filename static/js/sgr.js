(function () {
    const campo = document.querySelector("[data-autocompletar='solicitante']");
    if (!campo || !campo.form) {
        return;
    }
    const formulario = campo.form;
    const rut = formulario.querySelector("[data-autocompletar='rut']");
    const telefono = formulario.querySelector("[data-autocompletar='telefono']");
    const lista = document.createElement("div");
    lista.className = "list-group autocompletar-lista shadow";
    lista.hidden = true;
    campo.parentElement.classList.add("position-relative");
    campo.parentElement.appendChild(lista);
    let espera;
    campo.addEventListener("input", function () {
        window.clearTimeout(espera);
        const texto = campo.value.trim();
        if (texto.length < 2) {
            lista.hidden = true;
            return;
        }
        espera = window.setTimeout(function () {
            window.fetch("/servicios/personas/?q=" + encodeURIComponent(texto), {headers: {"X-Requested-With": "fetch"}})
                .then(function (respuesta) { return respuesta.json(); })
                .then(function (datos) {
                    lista.innerHTML = "";
                    (datos.resultados || []).forEach(function (item) {
                        const boton = document.createElement("button");
                        boton.type = "button";
                        boton.className = "list-group-item list-group-item-action";
                        boton.textContent = item.nombre + (item.rut ? " · " + item.rut : "") + (item.telefono ? " · " + item.telefono : "");
                        boton.addEventListener("click", function () {
                            campo.value = item.nombre;
                            if (rut && item.rut) {
                                rut.value = item.rut;
                            }
                            if (telefono && item.telefono) {
                                telefono.value = item.telefono;
                            }
                            lista.hidden = true;
                        });
                        lista.appendChild(boton);
                    });
                    lista.hidden = lista.children.length === 0;
                });
        }, 250);
    });
}());

(function () {
    const formulario = document.getElementById("filtros-tubo");
    const cuerpo = document.getElementById("cuerpo-tubo");
    const entrada = document.getElementById("q-agenda");
    if (!formulario || !cuerpo || !entrada) {
        return;
    }
    let espera;
    function actualizar() {
        const parametros = new URLSearchParams(new FormData(formulario));
        parametros.set("parcial", "1");
        window.fetch(formulario.action + "?" + parametros.toString(), {headers: {"X-Requested-With": "fetch"}})
            .then(function (respuesta) { return respuesta.text(); })
            .then(function (html) { cuerpo.innerHTML = html; });
    }
    entrada.addEventListener("input", function () {
        window.clearTimeout(espera);
        espera = window.setTimeout(actualizar, 250);
    });
    formulario.querySelectorAll("select, input[type='date']").forEach(function (control) {
        control.addEventListener("change", actualizar);
    });
}());

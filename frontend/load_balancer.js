const API_URL = "http://127.0.0.1:8000";

async function loadBalancer() {

    try {

        const response = await fetch(
            `${API_URL}/load-balancer`
        );

        if (!response.ok) {
            throw new Error("Failed to load balancer data");
        }

        const data = await response.json();

        document.getElementById("strategy").textContent =
            formatStrategy(data.strategy);

        document.getElementById("serverCount").textContent =
            data.servers.length;

        const totalVMs = data.servers.reduce(
            (total, server) =>
                total + server.active_vms,
            0
        );

        document.getElementById("vmCount").textContent =
            totalVMs;

        const averageLoad =
            data.servers.length
                ? data.servers.reduce(
                    (total, server) =>
                        total + server.load_score,
                    0
                ) / data.servers.length
                : 0;

        document.getElementById("averageLoad").textContent =
            `${averageLoad.toFixed(1)}%`;

        displayServers(data.servers);

    } catch (error) {

        console.error(error);

        document.getElementById("serverGrid").innerHTML = `
            <div class="server-card">
                Unable to load load balancer data.
            </div>
        `;
    }
}


function displayServers(servers) {

    const grid =
        document.getElementById("serverGrid");

    grid.innerHTML = "";

    servers
        .sort((a, b) =>
            a.load_score - b.load_score
        )
        .forEach(server => {

            const card =
                document.createElement("div");

            card.className = "server-card";

            card.innerHTML = `

                <div class="server-name">

                    <span>
                        ${server.name}
                    </span>

                    <span class="server-dot"></span>

                </div>


                <div class="metric">

                    <div class="metric-header">

                        <span>CPU</span>

                        <strong>
                            ${server.cpu_utilization}%
                        </strong>

                    </div>

                    <div class="progress">
                        <div
                            class="progress-fill"
                            style="width:${server.cpu_utilization}%"
                        ></div>
                    </div>

                </div>


                <div class="metric">

                    <div class="metric-header">

                        <span>RAM</span>

                        <strong>
                            ${server.ram_utilization}%
                        </strong>

                    </div>

                    <div class="progress">
                        <div
                            class="progress-fill"
                            style="width:${server.ram_utilization}%"
                        ></div>
                    </div>

                </div>


                <div class="load-score">

                    <span>LOAD SCORE</span>

                    <strong>
                        ${server.load_score}%
                    </strong>

                </div>

                <div class="load-score">

                    <span>ACTIVE VMS</span>

                    <strong>
                        ${server.active_vms}
                    </strong>

                </div>
            `;

            grid.appendChild(card);
        });
}


function formatStrategy(strategy) {

    if (strategy === "least_loaded") {
        return "Least Loaded";
    }

    return strategy;
}


loadBalancer();
const API_URL = "http://127.0.0.1:8000";


async function loadAutoScaling() {

    try {

        const response = await fetch(
            `${API_URL}/auto-scaling`
        );

        if (!response.ok) {
            throw new Error(
                "Failed to load auto scaling data"
            );
        }

        const data = await response.json();


        document.getElementById("status").textContent =
            data.scaling_needed
                ? "Scaling Required"
                : "Healthy";


        document.getElementById("currentServers").textContent =
            data.current_servers;


        document.getElementById("minimumServers").textContent =
            data.minimum_servers;


        document.getElementById("maximumServers").textContent =
            data.maximum_servers;


        document.getElementById("scaleUp").textContent =
            `${data.cpu_threshold}% CPU / ${data.ram_threshold}% RAM`;


        document.getElementById("scaleDown").textContent =
            "Disabled";


        document.getElementById("capacity").textContent =
            `${data.average_cpu}% CPU / ${data.average_ram}% RAM`;

    }

    catch (error) {

        console.error(error);

        document.getElementById("status").textContent =
            "Unavailable";

    }
}


loadAutoScaling();

setInterval(
    loadAutoScaling,
    3000
);
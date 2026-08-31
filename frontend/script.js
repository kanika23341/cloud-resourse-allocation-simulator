const API_URL = "http://127.0.0.1:8000";

const vmForm = document.getElementById("vmForm");
const resetButton = document.getElementById("resetButton");

const activeVMs = document.getElementById("activeVMs");
const cpuUtilization = document.getElementById("cpuUtilization");
const ramUtilization = document.getElementById("ramUtilization");
const hourlyCost = document.getElementById("hourlyCost");

const cpuChartValue = document.getElementById("cpuChartValue");
const ramChartValue = document.getElementById("ramChartValue");

const cpuBar = document.getElementById("cpuBar");
const ramBar = document.getElementById("ramBar");

const serverGrid = document.getElementById("serverGrid");

const allocationResult =
    document.getElementById("allocationResult");

async function loadDashboard() {

    await loadServers();

    await loadMetrics();

}

async function loadServers() {

    try {

        const response = await fetch(
            `${API_URL}/servers`
        );


        if (!response.ok) {

            throw new Error(
                `Server request failed: ${response.status}`
            );

        }


        const data = await response.json();


        displayServers(
            data.servers || []
        );


    } catch (error) {

        console.error(
            "Failed to load servers:",
            error
        );


        serverGrid.innerHTML = `

            <div class="empty-state">

                <div class="empty-icon">
                    !
                </div>

                <h4>
                    Could not load servers
                </h4>

                <p>
                    Make sure the FastAPI backend
                    is running.
                </p>

            </div>

        `;

    }

}

function displayServers(servers) {

    serverGrid.innerHTML = "";


    if (servers.length === 0) {

        serverGrid.innerHTML = `

            <div class="empty-state">

                <div class="empty-icon">
                    +
                </div>

                <h4>
                    No servers available
                </h4>

                <p>
                    Add servers to the simulation
                    to begin allocating VMs.
                </p>

            </div>

        `;

        return;

    }


    servers.forEach(server => {

        const serverCard =
            document.createElement("div");


        serverCard.className =
            "server-card";

        if (
            server.vms &&
            server.vms.length > 0
        ) {

            serverCard.classList.add(
                "active"
            );

        }


        const cpuUsed =
            server.total_cpu -
            server.available_cpu;


        const ramUsed =
            server.total_ram -
            server.available_ram;


        const cpuPercentage =
            calculatePercentage(
                cpuUsed,
                server.total_cpu
            );


        const ramPercentage =
            calculatePercentage(
                ramUsed,
                server.total_ram
            );


        serverCard.innerHTML = `

            <div class="server-title">

                <span class="server-name">
                    ${escapeHTML(server.name)}
                </span>

                <span class="server-status"></span>

            </div>


            <div class="resource">

                <div class="resource-info">

                    <span>
                        CPU
                    </span>

                    <strong>
                        ${server.available_cpu}
                        / ${server.total_cpu} cores
                    </strong>

                </div>


                <div class="progress-track">

                    <div
                        class="progress-fill"
                        style="width: ${cpuPercentage}%"
                    ></div>

                </div>

            </div>


            <div class="resource">

                <div class="resource-info">

                    <span>
                        MEMORY
                    </span>

                    <strong>
                        ${server.available_ram}
                        / ${server.total_ram} GB
                    </strong>

                </div>


                <div class="progress-track">

                    <div
                        class="progress-fill"
                        style="width: ${ramPercentage}%"
                    ></div>

                </div>

            </div>


            <div class="server-footer">

                <span>
                    ${server.vms ? server.vms.length : 0} VM
                    ${server.vms && server.vms.length !== 1 ? "s" : ""}
                </span>


                <strong>
                    Rs.${Number(server.cost_per_hour).toFixed(2)}/hr
                </strong>

            </div>

        `;


        serverGrid.appendChild(
            serverCard
        );

    });

}

async function loadMetrics() {

    try {

        const response = await fetch(
            `${API_URL}/metrics`
        );


        if (!response.ok) {

            throw new Error(
                `Metrics request failed: ${response.status}`
            );

        }


        const metrics =
            await response.json();


        const activeVMCount =
            Number(metrics.active_vms || 0);


        const cpuUsage =
            Number(
                metrics.cpu_utilization || 0
            );


        const ramUsage =
            Number(
                metrics.ram_utilization || 0
            );


        const cost =
            Number(
                metrics.hourly_cost || 0
            );
        activeVMs.textContent =
            activeVMCount;


        cpuUtilization.textContent =
            `${cpuUsage.toFixed(0)}%`;


        ramUtilization.textContent =
            `${ramUsage.toFixed(0)}%`;


        hourlyCost.textContent =
            `$${cost.toFixed(2)}`;

        cpuChartValue.textContent =
            `${cpuUsage.toFixed(0)}%`;


        ramChartValue.textContent =
            `${ramUsage.toFixed(0)}%`;


        cpuBar.style.width =
            `${Math.min(cpuUsage, 100)}%`;


        ramBar.style.width =
            `${Math.min(ramUsage, 100)}%`;


    } catch (error) {

        console.error(
            "Failed to load metrics:",
            error
        );

    }

}

vmForm.addEventListener(
    "submit",
    async function (event) {

        event.preventDefault();


        const vmName =
            document
                .getElementById("vmName")
                .value
                .trim();


        const cpu =
            Number(
                document
                    .getElementById("cpu")
                    .value
            );


        const ram =
            Number(
                document
                    .getElementById("ram")
                    .value
            );


        const duration =
            Number(
                document
                    .getElementById("duration")
                    .value
            );


        const algorithm =
            document
                .getElementById("algorithm")
                .value;
        if (!vmName) {

            displayAllocationError(
                "Please give your VM a name."
            );

            return;

        }


        if (
            !Number.isFinite(cpu) ||
            cpu <= 0
        ) {

            displayAllocationError(
                "CPU must be greater than zero."
            );

            return;

        }


        if (
            !Number.isFinite(ram) ||
            ram <= 0
        ) {

            displayAllocationError(
                "Memory must be greater than zero."
            );

            return;

        }


        if (
            !Number.isFinite(duration) ||
            duration <= 0
        ) {

            displayAllocationError(
                "Duration must be greater than zero."
            );

            return;

        }


        const vmRequest = {

            name: vmName,

            cpu: cpu,

            ram: ram,

            duration: duration,

            algorithm: algorithm

        };


        // Disable button while request is running

        const submitButton =
            vmForm.querySelector(
                "button[type='submit']"
            );


        const originalButtonText =
            submitButton.innerHTML;


        submitButton.disabled = true;


        submitButton.innerHTML = `

            <span>
                Finding a home...
            </span>

            <span>
                ...
            </span>

        `;


        try {

            const response = await fetch(
                `${API_URL}/allocate`,
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(
                            vmRequest
                        )

                }
            );


            const result =
                await response.json();


            if (
                response.ok &&
                result.success
            ) {

                displayAllocationResult(
                    result
                );


                await loadDashboard();


                vmForm.reset();


            } else {

                displayAllocationError(
                    result.message ||
                    "No suitable server was found."
                );

            }


        } catch (error) {

            console.error(
                "Allocation failed:",
                error
            );


            displayAllocationError(
                "Could not connect to the cloud simulator. Make sure the backend is running."
            );

        } finally {

            submitButton.disabled = false;

            submitButton.innerHTML =
                originalButtonText;

        }

    }
);

function displayAllocationResult(result) {

    const allocation =
        result.allocation || {};


    const vm =
        result.vm || {};


    const serverName =
        allocation.server ||
        allocation.server_name ||
        "Unknown server";


    const algorithm =
        allocation.algorithm ||
        vm.algorithm ||
        "best_fit";


    const estimatedCost =
        Number(
            allocation.estimated_cost || 0
        );


    allocationResult.innerHTML = `

        <div class="allocation-success">

            <div class="success-heading">

                <div class="success-check">
                    ✓
                </div>

                <div>

                    <strong>
                        VM found a home
                    </strong>

                </div>

            </div>


            <div class="allocation-details">


                <div class="detail-box">

                    <span>
                        VM
                    </span>

                    <strong>
                        ${escapeHTML(
                            vm.name || "Unknown"
                        )}
                    </strong>

                </div>


                <div class="detail-box">

                    <span>
                        SERVER
                    </span>

                    <strong>
                        ${escapeHTML(
                            serverName
                        )}
                    </strong>

                </div>


                <div class="detail-box">

                    <span>
                        CPU
                    </span>

                    <strong>
                        ${vm.cpu || 0} cores
                    </strong>

                </div>


                <div class="detail-box">

                    <span>
                        MEMORY
                    </span>

                    <strong>
                        ${vm.ram || 0} GB
                    </strong>

                </div>


                <div class="detail-box">

                    <span>
                        RUN TIME
                    </span>

                    <strong>
                        ${vm.duration || 0} hours
                    </strong>

                </div>


                <div class="detail-box">

                    <span>
                        ESTIMATED COST
                    </span>

                    <strong>
                        $${estimatedCost.toFixed(2)}
                    </strong>

                </div>


            </div>


            <div class="server-highlight">

                <span>
                    SCHEDULING STRATEGY
                </span>

                <strong>
                    ${formatAlgorithm(algorithm)}
                </strong>

            </div>


        </div>

    `;

}

function displayAllocationError(message) {

    allocationResult.innerHTML = `

        <div class="waiting">

            <div
                class="waiting-icon"
                style="
                    border-color: #e50914;
                    color: #e50914;
                "
            >
                !
            </div>


            <h3>
                Couldn't place the VM
            </h3>


            <p>
                ${escapeHTML(message)}
            </p>

        </div>

    `;

}

resetButton.addEventListener(
    "click",
    async function () {

        const originalText =
            resetButton.textContent;


        resetButton.disabled = true;

        resetButton.textContent =
            "Resetting...";


        try {

            const response =
                await fetch(
                    `${API_URL}/reset`,
                    {
                        method: "POST"
                    }
                );


            const result =
                await response.json();


            if (
                response.ok &&
                result.success
            ) {

                allocationResult.innerHTML = `

                    <div class="waiting">

                        <div class="waiting-icon">
                            ↻
                        </div>

                        <h3>
                            Playground reset
                        </h3>

                        <p>
                            All servers are ready
                            for new VM requests.
                        </p>

                    </div>

                `;


                await loadDashboard();

            } else {

                displayAllocationError(
                    result.message ||
                    "Could not reset the simulation."
                );

            }


        } catch (error) {

            console.error(
                "Reset failed:",
                error
            );


            displayAllocationError(
                "Could not connect to the backend."
            );


        } finally {

            resetButton.disabled = false;

            resetButton.textContent =
                originalText;

        }

    }
);

function calculatePercentage(
    used,
    total
) {

    if (
        !Number.isFinite(total) ||
        total <= 0
    ) {

        return 0;

    }


    const percentage =
        (used / total) * 100;


    return Math.min(
        Math.max(percentage, 0),
        100
    );

}


function formatAlgorithm(
    algorithm
) {

    const algorithmNames = {

        best_fit:
            "Best Fit",

        first_fit:
            "First Fit",

        greedy:
            "Greedy",

        knapsack:
            "Knapsack",

        branch_and_bound:
            "Branch & Bound",

        maximum_flow:
            "Maximum Flow"

    };


    return (
        algorithmNames[algorithm] ||
        algorithm
    );

}


function escapeHTML(value) {

    const temporaryElement =
        document.createElement("div");


    temporaryElement.textContent =
        String(value);


    return temporaryElement.innerHTML;

}

loadDashboard();
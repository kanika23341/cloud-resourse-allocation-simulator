const API_URL = "http://127.0.0.1:8000";

let instances = [];

const instanceGrid =
    document.getElementById("instanceGrid");

const instanceCount =
    document.getElementById("instanceCount");

const instanceSelect =
    document.getElementById("instanceSelect");

const runtimeInput =
    document.getElementById("runtimeInput");

const estimatedCost =
    document.getElementById("estimatedCost");

const costBreakdown =
    document.getElementById("costBreakdown");

async function loadInstances() {

    try {

        const response = await fetch(
            `${API_URL}/ec2/instances`
        );

        if (!response.ok) {

            throw new Error(
                "Failed to load EC2 instances"
            );

        }

        const data =
            await response.json();

        instances =
            data.instances || [];

        instanceCount.textContent =
            instances.length;

        populateSelect();

        displayInstances(instances);

    } catch (error) {

        console.error(error);

        instanceGrid.innerHTML = `

            <div class="error-state">

                <h3>
                    Unable to load instances
                </h3>

                <p>
                    Make sure the FastAPI backend
                    is running.
                </p>

            </div>

        `;

    }

}

function displayInstances(
    instanceList
) {

    instanceGrid.innerHTML = "";


    instanceList.forEach(instance => {

        const card =
            document.createElement("article");

        card.className =
            "instance-card";


        card.innerHTML = `

            <div class="instance-top">

                <span class="category">
                    ${instance.category}
                </span>

                <span class="instance-dot"></span>

            </div>


            <h3>
                ${instance.name}
            </h3>


            <div class="resources">

                <div>

                    <span>
                        vCPU
                    </span>

                    <strong>
                        ${instance.cpu}
                    </strong>

                </div>


                <div>

                    <span>
                        RAM
                    </span>

                    <strong>
                        ${instance.ram} GB
                    </strong>

                </div>

            </div>


            <div class="instance-bottom">

                <div>

                    <span>
                        HOURLY
                    </span>

                    <strong>
                        Rs.${instance.cost_per_hour.toFixed(4)}
                    </strong>

                </div>


                <button
                    onclick="selectInstance('${instance.name}')"
                >
                    Calculate
                </button>

            </div>

        `;


        instanceGrid.appendChild(card);

    });

}

function populateSelect() {

    instanceSelect.innerHTML = `

        <option value="">
            Select instance
        </option>

    `;


    instances.forEach(instance => {

        const option =
            document.createElement("option");

        option.value =
            instance.name;

        option.textContent =
            `${instance.name} — ${instance.cpu} vCPU / ${instance.ram} GB`;

        instanceSelect.appendChild(
            option
        );

    });

}

function selectInstance(
    instanceName
) {

    instanceSelect.value =
        instanceName;

    calculateCost();

    document
        .querySelector(".calculator")
        .scrollIntoView({
            behavior: "smooth"
        });

}

function calculateCost() {

    const selectedName =
        instanceSelect.value;

    const runtime =
        Number(runtimeInput.value);


    const selectedInstance =
        instances.find(
            instance =>
                instance.name === selectedName
        );


    if (
        !selectedInstance ||
        !runtime ||
        runtime <= 0
    ) {

        estimatedCost.textContent =
            "$0.00";

        costBreakdown.textContent =
            "Select an instance to calculate";

        return;

    }


    const totalCost =
        selectedInstance.cost_per_hour *
        runtime;


    estimatedCost.textContent =
        `$${totalCost.toFixed(2)}`;


    costBreakdown.textContent =
        `$${selectedInstance.cost_per_hour.toFixed(4)}/hr × ${runtime} hours`;

}

document
    .querySelectorAll(".filter")
    .forEach(button => {

        button.addEventListener(
            "click",
            function () {

                document
                    .querySelectorAll(".filter")
                    .forEach(
                        item =>
                            item.classList.remove(
                                "active"
                            )
                    );


                this.classList.add(
                    "active"
                );


                const category =
                    this.dataset.category;


                if (
                    category === "all"
                ) {

                    displayInstances(
                        instances
                    );

                } else {

                    const filtered =
                        instances.filter(
                            instance =>
                                instance.category ===
                                category
                        );

                    displayInstances(
                        filtered
                    );

                }

            }
        );

    });

instanceSelect.addEventListener(
    "change",
    calculateCost
);


runtimeInput.addEventListener(
    "input",
    calculateCost
);

loadInstances();
async function loadMenus() {
  const candidates = [
    "../data/current_menu.json",
    "/data/current_menu.json",
    "./data/current_menu.json",
  ];

  let lastError = null;
  for (const url of candidates) {
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) {
        lastError = new Error(`Cannot read data file at ${url}: ${response.status}`);
        continue;
      }
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Unable to load menu data");
}

function formatDate(iso, timezone) {
  const dt = new Date(iso);
  return new Intl.DateTimeFormat("cs-CZ", {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: timezone || "Europe/Prague",
  }).format(dt);
}

function formatMenuDay(data) {
  const menuDate = data.restaurants?.find((r) => r.menu_date)?.menu_date;
  const source = menuDate ? `${menuDate}T00:00:00` : data.generated_at;
  const dt = new Date(source);
  return new Intl.DateTimeFormat("cs-CZ", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: data.timezone || "Europe/Prague",
  }).format(dt);
}

function makeListItem(item) {
  const li = document.createElement("li");
  li.className = "menu-row";

  const title = document.createElement("span");
  title.className = "menu-title";
  title.textContent = item.title || "Polozka";
  li.appendChild(title);

  if (item.price) {
    const price = document.createElement("span");
    price.className = "price";
    price.textContent = item.price;
    li.appendChild(price);
  } else {
    li.classList.add("no-price");
  }

  return li;
}

function paint(data) {
  const meta = document.getElementById("meta");
  meta.textContent = `Aktualizovano: ${formatDate(data.generated_at, data.timezone)}`;

  const menuDay = document.getElementById("menu-day");
  menuDay.textContent = `Menu na: ${formatMenuDay(data)}`;

  const list = document.getElementById("restaurants");
  const template = document.getElementById("card-template");

  data.restaurants.forEach((restaurant) => {
    const node = template.content.cloneNode(true);
    node.querySelector(".name").textContent = restaurant.name;

    const status = node.querySelector(".status");
    status.textContent = restaurant.status;
    status.classList.add(restaurant.status);

    const menuList = node.querySelector(".menu-list");
    const items = restaurant.items || [];

    if (items.length === 0) {
      const li = document.createElement("li");
      li.textContent = "Menu pro dnes zatim neni k dispozici.";
      menuList.appendChild(li);
    } else {
      items.forEach((item) => menuList.appendChild(makeListItem(item)));
    }

    const src = node.querySelector(".source");
    src.href = restaurant.url;
    src.textContent = "otevrit web restaurace";

    list.appendChild(node);
  });
}

loadMenus().then(paint).catch((error) => {
  const list = document.getElementById("restaurants");
  const menuDay = document.getElementById("menu-day");
  menuDay.textContent = "Menu na: -";
  const openedFromFile = window.location.protocol === "file:";
  const help = openedFromFile
    ? "Open this app via a local HTTP server, not by double-clicking index.html."
    : "Check that data/current_menu.json exists and is reachable.";
  list.innerHTML = `<article class="card"><h2>Chyba</h2><p>${error.message}</p><p>${help}</p></article>`;
});

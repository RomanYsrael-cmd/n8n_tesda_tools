const fallbackFonts = [
  "Times New Roman", "Arial", "Calibri", "Cambria", "Georgia", "Verdana",
  "Tahoma", "Trebuchet MS", "Garamond", "Book Antiqua", "Century Gothic",
  "Courier New", "Consolas", "Segoe UI", "Palatino Linotype"
];

function populateFonts(families) {
  let list = document.querySelector("#available-fonts");
  if (!list) {
    list = document.createElement("datalist");
    list.id = "available-fonts";
    document.body.appendChild(list);
  }
  const unique = [...new Set([...fallbackFonts, ...families].filter(Boolean))].sort();
  list.replaceChildren(...unique.map(name => {
    const option = document.createElement("option");
    option.value = name;
    return option;
  }));
  document.querySelectorAll('input[name="font_family"]').forEach(input => input.setAttribute("list", list.id));
  return unique.length;
}

async function loadLocalFonts(button) {
  const message = button.parentElement.querySelector(".font-message");
  if (!("queryLocalFonts" in window)) {
    message.textContent = "This browser cannot list local fonts. You can still type any installed font name.";
    return;
  }
  try {
    const fonts = await window.queryLocalFonts();
    const count = populateFonts(fonts.map(font => font.family));
    message.textContent = `${count} font families are available in the picker.`;
  } catch (error) {
    message.textContent = "Font access was not allowed. You can still type an installed font name.";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  populateFonts([]);
  document.querySelectorAll('input[name="font_family"]').forEach(input => {
    const wrapper = document.createElement("div");
    wrapper.className = "actions";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = "Load fonts from this computer";
    button.addEventListener("click", () => loadLocalFonts(button));
    const message = document.createElement("small");
    message.className = "font-message";
    wrapper.append(button, message);
    input.insertAdjacentElement("afterend", wrapper);
    const warning = document.createElement("small");
    warning.textContent = "The DOCX will request this font. Docker's PDF preview may substitute it when that font is not installed inside the container.";
    wrapper.insertAdjacentElement("afterend", warning);
  });
});

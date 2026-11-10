// Petites aides pour construire le DOM. Tout texte venu du serveur passe par textContent.

export function el(tag, classe, texte) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texte !== undefined) e.textContent = texte;
  return e;
}

export function ligne(cle, valeur) {
  const l = el("div", "ligne");
  l.append(el("span", "cle", cle), el("span", "val", valeur));
  return l;
}

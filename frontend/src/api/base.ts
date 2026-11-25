/** URL de uma rota da API respeitando o prefixo em que o app é servido (Vite `base`, ex.: /kontrul-editor/gerador/). */
export const apiUrl = (path: string) => `${import.meta.env.BASE_URL}api${path}`

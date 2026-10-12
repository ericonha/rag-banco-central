import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

const API = 'http://localhost:8000/api';
const unique = () => Math.random().toString(36).slice(2, 8);

const input = (page: Page) => page.getByRole('textbox', { name: 'Escreva sua pergunta' });
const answers = (page: Page) => page.locator('article.turn-assistant');

async function ask(page: Page, question: string) {
  await input(page).fill(question);
  await input(page).press('Enter');
}

/** The answer is complete once the 👍/👎 buttons appear (they need the saved message id). */
async function waitForSavedAnswer(page: Page) {
  await expect(page.getByRole('button', { name: 'Resposta útil' }).last()).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.goto('/');
  await expect(input(page)).toBeVisible();
});

test('asks a question and streams a formatted, cited answer', async ({ page }) => {
  await ask(page, `O que diz a Resolução 598? ${unique()}`);

  const answer = answers(page).last();
  await expect(answer.locator('strong', { hasText: 'Resolução BCB nº 598' })).toBeVisible();
  await expect(answer.locator('table')).toBeVisible(); // Markdown table
  await expect(answer.locator('td', { hasText: '30 dias corridos' })).toBeVisible();
  await waitForSavedAnswer(page);

  // The [1] marker is a button that reveals the passage used.
  await answer.getByRole('button', { name: 'Fonte 1' }).first().click();
  await expect(answer.getByText('O prazo é de 30 dias corridos').first()).toBeVisible();

  // Faithful answer: no warning.
  await expect(page.locator('.grounding-warn')).toHaveCount(0);
});

test('thumbs down with a comment reaches the feedback log', async ({ page, request }) => {
  const comment = `faltou o prazo ${unique()}`;
  await ask(page, `pergunta para feedback ${unique()}`);
  await waitForSavedAnswer(page);

  await page.getByRole('button', { name: 'Resposta não útil' }).click();
  await page.getByRole('textbox', { name: /O que faltou/ }).fill(comment);
  await page.getByRole('button', { name: 'Enviar', exact: true }).click();

  await expect
    .poll(async () => {
      const res = await request.get(`${API}/admin/feedback`, { params: { value: -1, limit: 100 } });
      const data = await res.json();
      return data.items.some((i: { feedback_comment: string | null }) => i.feedback_comment === comment);
    })
    .toBe(true);
});

test('stop keeps the partial answer and frees the composer', async ({ page }) => {
  await ask(page, `uma resposta lenta ${unique()}`);

  await expect(answers(page).last()).toContainText('Parte 2');
  await page.getByRole('button', { name: 'Parar' }).click();

  await expect(page.getByRole('alert')).toContainText('Resposta interrompida');
  await expect(page.getByRole('button', { name: 'Enviar pergunta' })).toBeVisible();
  await expect(answers(page).last()).toContainText('Parte 1'); // what was streamed stays on screen
  await expect(answers(page).last()).not.toContainText('Parte 59');
});

test('regenerate replaces the answer, also after a reload', async ({ page }) => {
  await ask(page, `pergunta para regenerar ${unique()}`);
  await waitForSavedAnswer(page);
  const first = await answers(page).last().innerText();

  // scoped to the answer: the sidebar title of this conversation also contains "regenerar"
  await answers(page).last().getByRole('button', { name: 'Regenerar', exact: true }).click();
  await expect(answers(page)).toHaveCount(1);
  await expect(answers(page).last()).not.toHaveText(first);
  await waitForSavedAnswer(page);
  const second = await answers(page).last().innerText();

  // The server swapped the exchange instead of appending a second one.
  await page.reload();
  await expect(answers(page)).toHaveCount(1);
  await expect(page.locator('.turn-user')).toHaveCount(1);
  expect(await answers(page).last().innerText()).toContain(second.match(/versão \d+/)![0]);
});

test('finds the conversation by searching its text and exports it', async ({ page, request }) => {
  const word = `busca${unique()}`;
  await ask(page, `pergunta com a palavra ${word}`);
  await waitForSavedAnswer(page);
  await page.reload();

  const search = page.getByRole('searchbox', { name: 'Buscar conversas' });
  await search.fill('naoexistenenhuma' + unique());
  await expect(page.getByText('Nenhuma conversa encontrada.')).toBeVisible();

  await search.fill(word);
  const item = page.locator('.history-item', { hasText: word });
  await expect(item).toHaveCount(1);
  await search.fill('');

  await page.getByRole('button', { name: /Exportar/ }).click();
  const href = await page.getByRole('menuitem', { name: /Markdown/ }).getAttribute('href');
  expect(href).toContain('/export?format=md');
  const res = await request.get(href!);
  expect(res.ok()).toBe(true);
  expect(res.headers()['content-disposition']).toContain('attachment');
  const body = await res.text();
  expect(body).toContain(word);
  expect(body).toContain('Resolução BCB N° 598'); // sources are exported too
});

test('document-type filter restricts what the answer can use', async ({ page }) => {
  const select = page.getByLabel('Tipo de documento');
  await expect(select.locator('option', { hasText: 'Comunicado' })).toHaveCount(1);
  await select.selectOption('Comunicado');

  await ask(page, `pergunta filtrada ${unique()}`);
  await expect(answers(page).last()).toContainText('Nenhum documento relevante encontrado');

  await page.getByRole('button', { name: 'Limpar filtros' }).click();
  await ask(page, `pergunta sem filtro ${unique()}`);
  await expect(answers(page).last().locator('strong', { hasText: 'Resolução BCB nº 598' })).toBeVisible();
});

test('documents page lists the indexed documents and logs page draws the charts', async ({ page }) => {
  const nav = page.locator('.side-nav');
  await nav.getByRole('button', { name: 'Documentos' }).click();
  await expect(page.getByText('Resolução BCB N° 598').first()).toBeVisible();
  await expect(page.getByText('Comunicado N° 99.999').first()).toBeVisible();

  await nav.getByRole('button', { name: /Logs/ }).click();
  await page.getByRole('tab', { name: 'Tendências' }).click();
  await expect(page.locator('figure.chart')).toHaveCount(4);
  await expect(page.locator('figure.chart svg').first()).toBeVisible();
});

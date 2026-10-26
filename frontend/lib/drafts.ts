import type { Draft } from "./types";
const DB = "tallybinder-drafts";
function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () =>
      r.result.createObjectStore("drafts", { keyPath: "id" });
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}
export async function putDraft(draft: Draft) {
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("drafts", "readwrite");
      tx.objectStore("drafts").put(draft);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
export async function allDrafts(): Promise<Draft[]> {
  const db = await open();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction("drafts");
      const r = tx.objectStore("drafts").getAll();
      r.onsuccess = () =>
        resolve(
          r.result.sort((a: Draft, b: Draft) =>
            b.updated_at.localeCompare(a.updated_at),
          ),
        );
      r.onerror = () => reject(r.error);
    });
  } finally {
    db.close();
  }
}
export async function removeDraft(id: string) {
  const db = await open();
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("drafts", "readwrite");
      tx.objectStore("drafts").delete(id);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

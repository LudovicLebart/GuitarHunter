import { ref, uploadBytes, getDownloadURL } from 'firebase/storage';
import { storage } from './firebase';

// Décode un data URI base64 (format `inlineData` des messages du chat Gemini) en Blob, prêt pour
// un upload Firebase Storage.
export const base64ToBlob = async (base64Data, mimeType) => {
  const res = await fetch(`data:${mimeType};base64,${base64Data}`);
  return res.blob();
};

// Upload une photo jointe depuis le chat Gemini vers la galerie de l'annonce (2026-08-21). Même
// dossier que les photos scrapées côté backend (`deals/{dealId}/...`, voir
// backend/repository.py::upload_images_to_storage), préfixée `chat_` — préfixe exploité par
// storage.rules comme seul motif de nom autorisé en écriture côté client, garantissant qu'un
// fichier posé par le backend ne peut jamais être visé/écrasé depuis ce chemin.
export const uploadChatPhotoToDealStorage = async (dealId, blob, mimeType) => {
  const fileName = `chat_${Date.now()}_${crypto.randomUUID().slice(0, 8)}.jpg`;
  const fileRef = ref(storage, `deals/${dealId}/${fileName}`);
  await uploadBytes(fileRef, blob, { contentType: mimeType });
  // getDownloadURL() est indispensable ici : un upload via le SDK Web ne pose PAS l'ACL `publicRead`
  // que backend/repository.py pose via make_public() — une URL storage.googleapis.com construite à
  // la main serait en 403 partout (galerie, page de partage publique, chat).
  return getDownloadURL(fileRef);
};

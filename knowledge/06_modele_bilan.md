# Modèle de bilan SGO IMMO (07_Bilan_operation) et outil de calcul

Tu disposes de l'outil `simuler_operation`, qui reproduit exactement le classeur Excel
(onglets Bilan, Prix max, Sensibilités, Trésorerie). **Pour tout chiffre de bilan, de marge,
de prix maximal, de sensibilité ou de trésorerie, utilise l'outil : ne calcule pas de tête.**

## Conventions du modèle
- Montants HT, résultat **avant impôt sur les sociétés**.
- CA = surface vendable × prix de sortie HT/m² + autres recettes.
- Crédit = (prix + frais d'acquisition + travaux avec aléas) × quotité financée.
- Frais financiers (Bilan) calculés de façon **prudente** : crédit supposé entièrement débloqué
  sur toute la durée = crédit × taux × durée/12 + crédit × frais de dossier et garantie.
  L'onglet Trésorerie donne le coût **au fil de l'eau** (déblocage au prorata des dépenses),
  plus faible : présente les deux quand c'est utile.
- Fonds propres mobilisés = coût de revient − crédit (frais financiers payés sur fonds propres).
- Rentabilité des fonds propres = marge ÷ fonds propres ; annualisée = × 12 ÷ durée.
- Prix d'achat maximal = prix hors frais qui laisse exactement la marge cible (% du CA),
  toutes autres hypothèses inchangées. Marge de négociation positive = baisse de prix à obtenir.
- Trésorerie : mois 1 = acquisition, honoraires et frais de dossier ; travaux répartis entre le
  mois de début et le mois de fin ; intérêts mensuels sur l'encours ; remboursement et vente le
  dernier mois ; portage lissé. Durée limitée à 36 mois.
- Sensibilités de durée : taxes et charges de portage supposées proportionnelles à la durée.

## Valeurs par défaut du modèle (à signaler quand tu les utilises)
| Hypothèse | Défaut | Commentaire du modèle |
|---|---|---|
| Frais d'acquisition | 3 % du prix | Valeur indicative pour le régime MdB avec engagement de revendre : **à remplacer par le chiffrage du notaire** |
| Aléas travaux | 10 % | 10 à 15 % en rénovation lourde |
| Travaux | mois 2 à 6 | Mois 1 = acquisition |
| Frais de commercialisation | 0 % | Honoraires d'agence à la charge du vendeur, le cas échéant |
| TVA nette | 0 € | Régime (sur marge / sur prix total / exonéré) **à valider avec l'expert-comptable** |
| Quotité financée | 80 % | Selon l'accord bancaire |
| Taux | 5,5 % | Taux nominal du crédit |
| Frais de dossier et garantie | 1,5 % du crédit | Dossier, caution / hypothèque / PPD |
| Marge cible | 15 % du CA | Sert au calcul du prix d'achat maximal |

Ces défauts sont des hypothèses de travail, pas des vérités : si le client a un chiffre réel
(devis, accord de principe bancaire, chiffrage notaire), on prend le sien. Quand tu utilises
un défaut, dis-le dans ta réponse.

**Attention aux zéros** : honoraires et études, portage (taxe foncière, charges, assurance,
énergie) et TVA valent 0 par défaut dans l'outil. Une opération réelle n'a jamais zéro
honoraire ni zéro portage : si le client ne les donne pas, demande-les ou retiens une
estimation prudente **que tu annonces explicitement** comme hypothèse corrigée.

## Lecture des résultats
- Une marge nette sous la marge cible → calcule le prix d'achat maximal et la baisse à obtenir.
- Regarde le **cumul défavorable** : s'il est négatif, l'opération n'a pas de matelas de sécurité.
- Le point bas de trésorerie dit combien de fonds propres il faut réellement avoir disponibles,
  et quand.
- Un prix de sortie non justifié par des comparables rend tout le bilan fragile : dis-le.

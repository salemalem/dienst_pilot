---
id: regeln
title: Regelwerk der Abteilung (Annahmen des Prototyps)
language: de
synthetic: true
version: "Regelversion 2026-1"
source: synthetisch, erzeugt für DienstPilot; kein Tarifvertragstext
retrieved: 2026-10-22
---

Diese Zusammenfassung ist **synthetisch**. Sie beschreibt die Regelversion 2026-1 der fiktiven Klinik für Innere Medizin, Klinikum Musterstadt, wie der Prototyp sie anwendet. Es sind eigene Annahmen. Tarifvertragstext ist nicht enthalten; er ist urheberrechtlich geschützt und wird hier nicht wiedergegeben.

## [Regel 1] Ruhezeit
(1) Zwischen zwei Diensten liegen mindestens 11 Stunden ununterbrochene Ruhezeit (Regel min_rest_hours, angelehnt an § 5 ArbZG).
(2) Nach einem Bereitschaftsdienst folgt ein dienstfreier Tag (Regel free_day_after_on_call).

## [Regel 2] Nachtdienste
(1) Höchstens 3 Nachtdienste in Folge (Regel max_consecutive_nights). In der Regelversion 2021-1 waren es noch 4.
(2) Für Nachtdienst und Bereitschaftsdienst ist die Qualifikation nachtdienstfähig erforderlich. Im Bereitschaftsdienst muss mindestens eine Person Fachärztin oder Facharzt sein.

## [Regel 3] Wochenenden und Bereitschaft
(1) Höchstens 2 Wochenenden mit Dienst pro Person und Monat (Regel max_weekends_per_month).
(2) Höchstens 4 Bereitschaftsdienste im Krankenhaus pro Person und Monat (Regel max_on_call_per_month) und höchstens 10 Bereitschaften zu Hause (Regel max_on_call_home_per_month).
(3) Ein Bereitschaftsdienst wird mit 18 Stunden angerechnet (Regel bereitschaft_credited_hours).

## [Regel 4] Vertragsstunden
(1) Die Monatsstunden liegen zwischen 80 % und 110 % der Vertragsstunden (Regel contract_hours_band).
(2) Das Unterschreiten des Bandes durch das Abgeben eines Dienstes führt dazu, dass die Planung entscheidet; ein Tausch gegen einen anderen Dienst erhält die Stunden.

## [Regel 5] Rufbereitschaft
(1) Die Rufbereitschaft wird von Oberärztinnen und Oberärzten übernommen (Regel qualification_mix, Schicht ruf).

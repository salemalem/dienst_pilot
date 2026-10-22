---
id: sop
title: Standardarbeitsanweisungen der Abteilung (synthetisch)
language: de
synthetic: true
version: "SOP-Stand 2026-10"
source: synthetisch, erzeugt für DienstPilot
retrieved: 2026-10-22
---

Diese Arbeitsanweisungen sind **synthetisch** und beschreiben, wie der Prototyp den Ablauf abbildet.

## [SOP-1] Krankmeldung und Vertretungssuche
(1) Wer sich krank meldet, gibt nur Datum von und bis an. Es gibt kein Feld für eine Diagnose.
(2) Für jeden Dienst im Zeitraum, der noch nicht begonnen hat, startet die Vertretungssuche. Das System prüft, wer qualifiziert, dienstfrei und regelkonform einspringen darf, und ordnet die Kolleginnen und Kollegen nach der bisherigen Vertretungsbelastung.
(3) Die erste Person wird gefragt und hat 15 Minuten Zeit. Antwortet sie nicht, wird die nächste gefragt.
(4) Sagt jemand zu, prüft das System den Plan erneut. Bleibt alles regelkonform und entstehen keine Überstunden, bestätigt die Richtlinie der Planung die Übernahme. Sonst entscheidet die Planung.
(5) Ist die Liste erschöpft, gibt die Planung eine Entscheidung mit den geordneten Optionen und deren Folgen.

## [SOP-2] Diensttausch
(1) Wer einen Dienst abgeben möchte, bietet ihn an. Das Angebot geht nur an Kolleginnen und Kollegen, die ihn regelkonform übernehmen können.
(2) Nimmt jemand das Angebot an, allein oder im Tausch gegen einen eigenen Dienst, prüft das System beide Dienstpläne.
(3) Ist alles gültig und die automatische Freigabe eingeschaltet, ist der Tausch bestätigt. Andernfalls erscheint er mit Grund im Posteingang der Planung (zum Beispiel hours_band oder rule_violation).

## [SOP-3] Wunschphase
(1) Die Wunschphase öffnet sechs Wochen vor dem Monat und dauert 14 Tage.
(2) Wer bis 7 Tage und noch einmal bis 2 Tage vor dem Ende nicht geantwortet hat, erhält eine Erinnerung in der App. Die Planung kann zusätzlich jederzeit manuell erinnern.
(3) Nach dem Schließen der Wunschphase berechnet das System zwei bis drei gültige Varianten. Ein Lauf bei offener Wunschphase ist ein Probelauf.

## [SOP-4] Monatsabschluss
(1) Sobald ein Monat vorbei ist, erstellt das System die Dokumentation: Stunden, Überstunden, Ruhezeiten, Verteilung von Nacht-, Wochenend- und Feiertagsdiensten und den Entscheidungsverlauf.
(2) Die Planung bestätigt die Dokumentation mit einem Klick. Damit ist der Monat abgeschlossen und der Lohnexport freigegeben.

## [SOP-5] Änderung an einem veröffentlichten Plan
(1) Die Planung ändert nur künftige Tage und gibt eine Begründung an.
(2) Das System lehnt eine Änderung ab, die eine Regel verletzt, und benennt die Regel.
(3) Alle betroffenen Personen werden benachrichtigt, und die Änderung steht im Protokoll.

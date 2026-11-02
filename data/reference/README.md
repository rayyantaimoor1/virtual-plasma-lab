# Reference data

`manifest.json` lists every data set with its source, citation, retrieval date and SHA-256 checksum. The loaders refuse a file whose checksum does not match.

| Data | In this repository? | Why | How to get it |
|---|---|---|---|
| Molecular constants, benchmark values | Yes | A small set of cited values | Already here |
| NIST atomic lines | No | NIST holds copyright in this compilation, and this repository is public | `python scripts/fetch_reference.py nist` |
| LXCat cross-sections | No | [LXCat does not authorise third parties to redistribute its data](https://nl.lxcat.net/instructions/redistribution.php) | Download it yourself, as below |

After a download, a checksum mismatch means your file differs from the one recorded. For NIST, that usually means NIST updated its data. Find out what changed before accepting the new file, because results may change.

## Downloading the LXCat file

LXCat asks each person to confirm that they understand its policy and will reference the data, and it uses a human-verification check. Each team member must do this personally.

These are the steps used for the recorded file on 2 November 2026. The **Next** button can take several seconds to respond, so click it once and wait.

1. Go to <https://www.lxcat.net> and open **Data center → Browse and download**.
2. Choose **Scattering cross sections** and press **Next**.
3. Press the **−** button beside "Select all & filter tool" to clear every database, click **Biagi (transcription of data from SF Biagi's Fortran code, Magboltz.)**, and press **Next**. If you pick another database, tell the rest of the team, because the physics results depend on it.
4. The first species (electrons) is chosen for you. On the second species, click **Ar**, **N2** and **O2**, and press **Next**.
5. On data groups, press **+** to select all four (attachment, elastic, excitation, ionization), and press **Next**.
6. On processes, press **+** to select all 107, and press **Next**.
7. LXCat shows its terms of use. Read them, and press **YES, I have read and understood** only if you agree. It returns you to processes; press **Next** again.
8. On the output page, click the **TXT** link and save the file, for example as `lxcat_download.txt`.
9. Run `python scripts/fetch_reference.py lxcat lxcat_download.txt`.

Reports must cite the database, www.lxcat.net and the retrieval date, as [LXCat requires](https://nl.lxcat.net/instructions/how_reference.php). The citation recorded in `manifest.json` comes from the file's header, including the MAGBOLTZ version Biagi asks to be named.

LXCat writes the download date into the header, so each person's file differs and will not match the recorded checksum. Before accepting a teammate's file, compare it with the recorded one, ignoring the date line.

**Note for the physics code:** in this file the O2 three-body attachment cross-section is "normalized to gas density in units of 1/cm3", so it is not a plain area in m². Its comment is kept in `CrossSection.comments`.

## Benchmarks

A value goes into `constants/benchmarks.csv` only after it has been read in the source, and the values are committed before any model result is compared with them (ACC-1, ACC-4).

Recorded on 2 November 2026, before the Phase 2 model existed: Saikia et al., *AIP Advances* 8, 045113 (2018), open access (CC BY 4.0). These are argon at 13.56 MHz, measured with an RF-compensated Langmuir probe:
- Table II, 50 W at 100, 200, 300 and 400 mTorr. The first three (0.13, 0.27 and 0.40 mbar) are inside our 0.1–0.5 mbar envelope.
- Table I, 10–50 W at 73 mTorr (0.097 mbar), just below the envelope. Recorded for trends only.

Their discharge is asymmetric (8 cm and 10 cm electrodes, 7.5 cm apart), so the model is run in that geometry when it is compared with them.

The publisher's page shows a human-verification check in a browser, so the values were read from the page text downloaded by a web tool. Two separate reads gave the same numbers. Anyone with library access should check them once against the PDF tables.

More papers to check, through the COMSATS library or the HEC Digital Library:

- V. A. Godyak, R. B. Piejak and B. M. Alexandrovich, *Plasma Sources Sci. Technol.* 1, 36 (1992). DOI: 10.1088/0963-0252/1/1/006. Argon at 13.56 MHz from 3 mTorr to 3 Torr; the most likely source.
- *Langmuir Probe Measurements in the Gaseous Electronics Conference RF Reference Cell*, PMC article PMC4887235. Includes argon at 100 mTorr.
- *The discharge characteristics of low-pressure capacitively coupled argon plasma with Langmuir probe*, ScienceDirect article S0375960121007751.
- Work from the COMSATS Plasma Research Laboratory: Anjum and Rehman, *AIP Advances* 10 (2020), and Anjum, Younus and Rehman, *Physica Scripta* 95 (2020).

Phase 7 also needs at least one published *E. coli* survival result for the underwater discharge (ACC-1), and time-resolved data for the Hom model.

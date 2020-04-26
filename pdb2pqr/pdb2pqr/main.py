"""Driver for PDB2PQR

This module takes a PDB file as input and performs optimizations before yielding a new PDB-style file as output.
"""

# TODO - would be nice to remove os package
import os
import time
import logging
from pathlib import Path
import argparse
from . import pdb, cif, utilities, structures, routines, protein, definitions
from . import aa, hydrogens, forcefield, na
from io import StringIO
from .errors import PDB2PQRError
from .propka import lib as propka_lib
from . import extensions
from . import __version__
from .pdb2pka.ligandclean import ligff


HEADER_TEXT = """
-------------------------------------------
PDB2PQR - biomolecular structure conversion
Version {version}
-------------------------------------------
Please cite your use of PDB2PQR as:

  Dolinsky TJ, Nielsen JE, McCammon JA, Baker NA. PDB2PQR: an automated
  pipeline for the setup, execution, and analysis of Poisson-Boltzmann
  electrostatics calculations. Nucleic Acids Research 32 W665-W667 (2004).
"""
HEADER_TEXT = HEADER_TEXT.format(version=__version__)
FIELD_NAMES = ('amber', 'charmm', 'parse', 'tyl06', 'peoepb', 'swanson')
_LOGGER = logging.getLogger(__name__)
logging.captureWarnings(True)


# TODO - needs docstring
def getOldHeader(pdblist):
    oldHeader = StringIO()
    headerTypes = (HEADER, TITLE, COMPND, SOURCE,
                   KEYWDS, EXPDTA, AUTHOR, REVDAT,
                   JRNL, REMARK, SPRSDE, NUMMDL)
    for pdbObj in pdblist:
        if not isinstance(pdbObj,headerTypes):
            break

        oldHeader.write(str(pdbObj))
        oldHeader.write('\n')

    return oldHeader.getvalue()


# TODO - needs docstring
def printPQRHeader(pdblist,
                   atomlist,
                   reslist,
                   charge,
                   ff,
                   ph_calc_method,
                   pH,
                   ffout,
                   include_old_header=False):
    """
        Print the header for the PQR file

        Parameters:
            atomlist: A list of atoms that were unable to have
                      charges assigned (list)
            reslist:  A list of residues with non-integral charges
                      (list)
            charge:   The total charge on the protein (float)
            ff:       The forcefield name (string)
            pH :  pH value, if any. (float)
            ffout :  ff used for naming scheme (string)
        Returns
            header:   The header for the PQR file (string)
    """
    if ff is None:
        ff = 'User force field'
    else:
        ff = ff.upper()
    header = "REMARK   1 PQR file generated by PDB2PQR (Version %s)\n" % __version__
    header = header + "REMARK   1\n"
    header = header + "REMARK   1 Forcefield Used: %s\n" % ff
    if not ffout is None:
        header = header + "REMARK   1 Naming Scheme Used: %s\n" % ffout
    header = header + "REMARK   1\n"

    if ph_calc_method is not None:
        header = header + "REMARK   1 pKas calculated by %s and assigned using pH %.2f\n" % (ph_calc_method, pH)
        header = header + "REMARK   1\n"

    if len(atomlist) != 0:
        header += "REMARK   5 WARNING: PDB2PQR was unable to assign charges\n"
        header += "REMARK   5          to the following atoms (omitted below):\n"
        for atom in atomlist:
            header += "REMARK   5              %i %s in %s %i\n" % \
                      (atom.get("serial"), atom.get("name"), \
                       atom.get("residue").get("name"), \
                       atom.get("residue").get("resSeq"))
        header += "REMARK   5 This is usually due to the fact that this residue is not\n"
        header += "REMARK   5 an amino acid or nucleic acid; or, there are no parameters\n"
        header += "REMARK   5 available for the specific protonation state of this\n"
        header += "REMARK   5 residue in the selected forcefield.\n"
        header += "REMARK   5\n"
    if len(reslist) != 0:
        header += "REMARK   5 WARNING: Non-integral net charges were found in\n"
        header += "REMARK   5          the following residues:\n"
        for residue in reslist:
            header += "REMARK   5              %s - Residue Charge: %.4f\n" % \
                      (residue, residue.getCharge())
        header += "REMARK   5\n"
    header += "REMARK   6 Total charge on this protein: %.4f e\n" % charge
    header += "REMARK   6\n"

    if include_old_header:
        header += "REMARK   7 Original PDB header follows\n"
        header += "REMARK   7\n"

        header += getOldHeader(pdblist)

    return header


# TODO - needs docstring
def printPQRHeaderCIF(pdblist,
                      atomlist,
                      reslist,
                      charge,
                      ff,
                      ph_calc_method,
                      pH,
                      ffout,
                      include_old_header=False):

    """
        Print the header for the PQR file in cif format.

        Paramaters:
            atomlist: A list of atoms that were unable to have
                      charges assigned (list)
            reslist:  A list of residues with non-integral charges
                      (list)
            charge:   The total charge on the protein (float)
            ff:       The forcefield name (string)
            pH :  pH value, if any. (float)
            ffout :  ff used for naming scheme (string)
        Returns
            header:   The header for the PQR file (string)
    """

    if(ff is None):
        ff = "User force field"
    else:
        ff = ff.upper()

    header = "#\n"
    header += "loop_\n"
    header += "_pdbx_database_remark.id\n"
    header += "_pdbx_database_remark.text\n"
    header += "1\n"
    header += ";\n"
    header += "PQR file generated by PDB2PQR (Version %s)\n" % __version__
    header += "\n"
    header += "Forcefiled used: %s\n" % ff
    if(not ffout is None):
        header += "Naming scheme used: %s\n" % ffout
    header += "\n"
    if(ph_calc_method is not None):
        header += "pKas calculated by %s and assigned using pH %.2f\n" % (ph_calc_method, pH)
    header += ";\n"
    header +="2\n"
    header +=";\n"
    if len(atomlist) > 0:
        header += "Warning: PDB2PQR was unable to assign charges\n"
        header += "to the following atoms (omitted below):\n"
        for atom in atomlist:
            header += "             %i %s in %s %i\n" % \
                      (atom.get("serial"), atom.get("name"), \
                       atom.get("residue").get("name"), \
                       atom.get("residue").get("resSeq"))
        header += "This is usually due to the fat thtat this residue is not\n"
        header += "an amino acid or nucleic acid; or, there are no parameters\n"
        header += "available for the specific protonation state of this\n"
        header += "residue in the selected forcefield.\n"
    if len(reslist) > 0:
        header += "\n"
        header += "Warning: Non-integral net charges were found in\n"
        header += "the following residues:\n"
        for residue in reslist:
            header += "              %s - Residue Charge: %.4f\n" % \
                      (residue, residue.getCharge())
    header += ";\n"
    header += "3\n"
    header += ";\n"
    header += "Total charge on this protein: %.4f e\n" % charge
    header += ";\n"
    if include_old_header:
        header += "4\n"
        header += ";\n"
        header += "Including original cif header is not implemented yet.\n"
        header += ";\n"
    header += "#\n"
    header += "loop_\n"
    header += "_atom_site.group_PDB\n"
    header += "_atom_site.id\n"
    header += "_atom_site.label_atom_id\n"
    header += "_atom_site.label_comp_id\n"
    header += "_atom_site.label_seq_id\n"
    header += "_atom_site.Cartn_x\n"
    header += "_atom_site.Cartn_y\n"
    header += "_atom_site.Cartn_z\n"
    header += "_atom_site.pqr_partial_charge\n"
    header += "_atom_site.pqr_radius\n"

    return header


# TODO - needs docstring
def runPDB2PQR(pdblist, options):
    """
        Run the PDB2PQR Suite

        Args:
            pdblist: The list of objects that was read from the PDB file
                     given as input (list)
            options:      The name of the forcefield (string)

        Returns
            header:  The PQR file header (string)
            lines:   The PQR file atoms (list)
            missedligandresidues:  A list of ligand residue names whose charges could
                     not be assigned (ligand)
            protein: The protein object
    """

    pkaname = ""
    lines = []
    Lig = None
    atomcount = 0   # Count the number of ATOM records in pdb

    outroot = utilities.getPQRBaseFileName(options.output_pqr)

    if options.pka_method == 'propka':
        pkaname = outroot + ".propka"
        #TODO: What? Shouldn't it be up to propka on how to handle this?
        if os.path.isfile(pkaname):
            os.remove(pkaname)

    start = time.time()
    _LOGGER.info("Beginning PDB2PQR...")

    myDefinition = definitions.Definition()
    _LOGGER.info("Parsed Amino Acid definition file.")

    if options.drop_water:
        # Remove the waters
        pdblist_new = []
        for record in pdblist:
            if isinstance(record, (HETATM, ATOM, SIGATM, SEQADV)):
                if record.resName in aa.WAT.water_residue_names:
                    continue
            pdblist_new.append(record)

        pdblist = pdblist_new

    # Check for the presence of a ligand!  This code is taken from pdb2pka/pka.py

    if options.ligand is not None:
        myProtein, myDefinition, Lig = ligff.initialize(myDefinition,
                                                        options.ligand,
                                                        pdblist)
        for atom in myProtein.getAtoms():
            if atom.type == "ATOM":
                atomcount += 1
    else:
        myProtein = protein.Protein(pdblist, myDefinition)

    _LOGGER.info("Created protein object -")
    _LOGGER.info("\tNumber of residues in protein: %s", myProtein.numResidues())
    _LOGGER.info("\tNumber of atoms in protein   : %s", myProtein.numAtoms())

    myRoutines = routines.Routines(myProtein)

    for residue in myProtein.getResidues():
        multoccupancy = 0
        for atom in residue.getAtoms():
            if atom.altLoc != "":
                multoccupancy = 1
                txt = "Warning: multiple occupancies found: %s in %s\n" % (atom.name, residue)
                _LOGGER.warn(txt)
        if multoccupancy == 1:
            _LOGGER.warn("WARNING: multiple occupancies found in %s,\n" % (residue))
            _LOGGER.warn("         at least one of the instances is being ignored.\n")

    myRoutines.setTermini(options.neutraln, options.neutralc)
    myRoutines.updateBonds()

    if options.clean:
        header = ""
        lines = myProtein.printAtoms(myProtein.getAtoms(), options.chain)

        # Process the extensions
        for ext in options.active_extensions:
            module = extensions.extDict[ext]
            module.run_extension(myRoutines, outroot, extensionOptions)

        _LOGGER.debug("Total time taken: %.2f seconds", (time.time() - start))

        #Be sure to include None for missed ligand residues
        return header, lines, None

    #remove any future need to convert to lower case
    if options.ff is not None:
        ff = options.ff.lower()
    if options.ffout is not None:
        ffout = options.ffout.lower()

    if not options.assign_only:
        # It is OK to process ligands with no ATOM records in the pdb
        if atomcount == 0 and Lig != None:
            pass
        else:
            myRoutines.findMissingHeavy()
        myRoutines.updateSSbridges()

        if options.debump:
            myRoutines.debumpProtein()

        if options.pka_method == 'propka':
            myRoutines.runPROPKA(ph, ff, outroot, pkaname, ph_calc_options, version=31)
        elif options.pka_method == 'pdb2pka':
            myRoutines.runPDB2PKA(ph, ff, pdblist, ligand, ph_calc_options)

        myRoutines.addHydrogens()

        myhydRoutines = hydrogens.hydrogenRoutines(myRoutines)

        if options.debump:
            myRoutines.debumpProtein()

        if options.opt:
            myhydRoutines.setOptimizeableHydrogens()
            # TONI fixing residues - myhydRoutines has a reference to myProtein, so i'm altering it in place
            myRoutines.holdResidues(None)
            myhydRoutines.initializeFullOptimization()
            myhydRoutines.optimizeHydrogens()
        else:
            myhydRoutines.initializeWaterOptimization()
            myhydRoutines.optimizeHydrogens()

        # Special for GLH/ASH, since both conformations were added
        myhydRoutines.cleanup()


    else:  # Special case for HIS if using assign-only
        for residue in myProtein.getResidues():
            if isinstance(residue, aa.HIS):
                myRoutines.applyPatch("HIP", residue)

    myRoutines.setStates()

    myForcefield = forcefield.Forcefield(ff, myDefinition, options.userff,
                                         options.usernames)
    hitlist, misslist = myRoutines.applyForcefield(myForcefield)

    ligsuccess = 0

    if options.ligand is not None:
        # If this is independent, we can assign charges and radii here
        for residue in myProtein.getResidues():
            if isinstance(residue, LIG):
                templist = []
                Lig.make_up2date(residue)
                for atom in residue.getAtoms():
                    atom.ffcharge = Lig.ligand_props[atom.name]["charge"]
                    atom.radius = Lig.ligand_props[atom.name]["radius"]
                    if atom in misslist:
                        misslist.pop(misslist.index(atom))
                        templist.append(atom)

                charge = residue.getCharge()
                if abs(charge - int(charge)) > 0.001:
                    # Ligand parameterization failed
                    _LOGGER.warn("WARNING: PDB2PQR could not successfully parameterize the desired ligand; it has been left out of the PQR file.")

                    # remove the ligand
                    myProtein.residues.remove(residue)
                    for myChain in myProtein.chains:
                        if residue in myChain.residues: myChain.residues.remove(residue)
                else:
                    ligsuccess = 1
                    # Mark these atoms as hits
                    hitlist = hitlist + templist

    # Temporary fix; if ligand was successful, pull all ligands from misslist
    if ligsuccess:
        templist = misslist[:]
        for atom in templist:
            if isinstance(atom.residue, (aa.Amino, na.Nucleic)):
                continue
            misslist.remove(atom)

    # Create the Typemap
    if options.typemap:
        typemapname = "%s-typemap.html" % outroot
        myProtein.createHTMLTypeMap(myDefinition, typemapname)

    # Grab the protein charge
    reslist, charge = myProtein.getCharge()

    # If we want a different naming scheme, use that

    if options.ffout is not None:
        scheme = ffout
        userff = None # Currently not supported
        if scheme != ff:
            myNameScheme = Forcefield(scheme, myDefinition, userff)
        else:
            myNameScheme = myForcefield
        myRoutines.applyNameScheme(myNameScheme)

    if(options.isCIF):
        header = printPQRHeaderCIF(pdblist, misslist, reslist, charge, ff,
                            options.pka_method, options.ph, options.ffout,
                            include_old_header=options.include_header)
    else:
        header = printPQRHeader(pdblist, misslist, reslist, charge, ff,
                            options.pka_method, options.ph, options.ffout,
                            include_old_header=options.include_header)

    lines = myProtein.printAtoms(hitlist, options.chain)

    # Determine if any of the atoms in misslist were ligands
    missedligandresidues = []
    for atom in misslist:
        if isinstance(atom.residue, (aa.Amino, na.Nucleic)):
            continue
        if atom.resName not in missedligandresidues:
            missedligandresidues.append(atom.resName)

    # Process the extensions
    for ext in options.active_extensions:
        module = extensions.extDict[ext]
        module.run_extension(myRoutines, outroot, extensionOptions)

    _LOGGER.debug("Total time taken: %.2f seconds", (time.time() - start))

    return header, lines, missedligandresidues


def build_parser():
    """Build an argument parser.

    Return:
        ArgumentParser() object
    """

    desc = "Wields awesome powers to turn PDBs into PQRs."
    p = argparse.ArgumentParser(description=desc,
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("input_pdb",
                   help="Input PDB path or ID (to be retrieved from RCSB database")
    p.add_argument("output_pqr", help="Output PQR path")
    p.add_argument("--log-level", help="Logging level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    g1 = p.add_argument_group(title="Mandatory options",
                             description="One of the following options must be used")
    g1.add_argument("--ff", choices=[x.upper() for x in FIELD_NAMES],
                   help="The forcefield to use.")
    g1.add_argument("--userff",
                   help="The user-created forcefield file to use. Requires --usernames and overrides --ff")
    g1.add_argument("--clean", action='store_true', default=False,
                   help="Do no optimization, atom addition, or parameter assignment, just return the original PDB file in aligned format. Overrides --ff and --userff")
    g2 = p.add_argument_group(title="General options")
    g2.add_argument('--nodebump', dest='debump', action='store_false',
                    default=True, help='Do not perform the debumping operation')
    g2.add_argument('--noopt', dest='opt', action='store_false', default=True,
                    help='Do not perform hydrogen optimization')
    g2.add_argument('--chain', action='store_true', default=False,
                    help='Keep the chain ID in the output PQR file')
    g2.add_argument('--assign-only', action='store_true', default=False,
                    help='Only assign charges and radii - do not add atoms, debump, or optimize.')
    g2.add_argument('--ffout', choices=[x.upper() for x in FIELD_NAMES],
                    help='Instead of using the standard canonical naming scheme for residue and atom names, use the names from the given forcefield')
    g2.add_argument('--usernames', 
                    help='The user created names file to use. Required if using --userff')
    g2.add_argument('--apbs-input', action='store_true', default=False,
                    help='Create a template APBS input file based on the generated PQR file.  Also creates a Python pickle for using these parameters in other programs.')
    g2.add_argument('--ligand',
                    help='Calculate the parameters for the specified MOL2-format ligand at the path specified by this option.  PDB2PKA must be compiled.')
    g2.add_argument('--whitespace', action='store_true', default=False,
                    help='Insert whitespaces between atom name and residue name, between x and y, and between y and z.')
    g2.add_argument('--typemap', action='store_true', default=False,
                    help='Create Typemap output.')
    g2.add_argument('--neutraln', action='store_true', default=False,
                    help='Make the N-terminus of this protein neutral (default is charged). Requires PARSE force field.')
    g2.add_argument('--neutralc', action='store_true', default=False,
                    help='Make the C-terminus of this protein neutral (default is charged). Requires PARSE force field.')
    g2.add_argument('--drop-water', action='store_true', default=False,
                    help='Drop waters (%s) before processing protein.' % aa.WAT.water_residue_names)

    g2.add_argument('--include-header', action='store_true', default=False,
                    help='Include pdb header in pqr file. WARNING: The resulting PQR file will not work with APBS versions prior to 1.5')
    g3 = p.add_argument_group(title="pKa options",
                              description="Options for titration calculations")
    g3.add_argument('--titration-state-method', dest="pka_method", 
                    choices=('propka', 'pdb2pka'),
                    help='Method used to calculate titration states. If a titration state method is selected, titratable residue charge states will be set by the pH value supplied by --with_ph')
    g3.add_argument('--with-ph', dest='ph', type=float, action='store', default=7.0,
                    help='pH values to use when applying the results of the selected pH calculation method.')
    g4 = p.add_argument_group(title="PDB2PKA method options")
    g4.add_argument('--pdb2pka-out', default='pdb2pka_output',
                    help='Output directory for PDB2PKA results.')
    g4.add_argument('--pdb2pka-resume', action="store_true", default=False,
                    help='Resume run from state saved in output directory.')
    g4.add_argument('--pdie', default=8.0,
                    help='Protein dielectric constant.')
    g4.add_argument('--sdie', default=80.0,
                    help='Solvent dielectric constant.')
    g4.add_argument('--pairene',  default=1.0,
                    help='Cutoff energy in kT for pairwise pKa interaction energies.')
    g5 = p.add_argument_group(title="PROPKA method options")
    g5.add_argument("--propka-reference", default="neutral", choices=('neutral','low-pH'),
                    help="Setting which reference to use for stability calculations. See PROPKA 3.0 documentation.")
    return p


def mainCommand():
    """Main driver for running program from the command line."""

    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level))

    _LOGGER.debug("Args:  %s", args)
    _LOGGER.info(HEADER_TEXT)

    if args.assign_only or args.clean:
        args.debump = False
        args.opt = False

    if not args.clean:
        if args.usernames is not None:
            # TODO - it makes me sad to open a file without a close() statement
            user_names_file = open(args.usernames, 'rt', encoding="utf-8")
        if args.userff is not None:
            # TODO - it makes me sad to open a file without a close() statement
            user_ff_file = open(args.userff, "rt", encoding="utf-8")
            if args.usernames is None:
                parser.error(message='--usernames must be specified if using --userff')
        if utilities.getFFfile(args.ff) == "":
            parser.error(message="Unable to load parameter file for forcefield %s" % args.ff)
        if (args.ph < 0) or (args.ph > 14):
            parser.error(message="Specified pH (%s) is outside the range [1, 14] of this program" % args.ph)
    
    ph_calc_options = None

    if args.pka_method == 'propka':
        ph_calc_options, _ = propka_lib.loadOptions('--quiet')
    elif args.pka_method == 'pdb2pka':
        if args.ff.lower() != 'parse':
            parser.error('PDB2PKA requires the PARSE force field.')
        ph_calc_options = {'output_dir': args.output_pqr,
                          'clean_output': not args.pdb2pka_resume,
                          'pdie': args.pdie,
                          'sdie': args.sdie,
                          'pairene': args.pairene}

    if args.ligand is not None:
        try:
            # TODO - it makes me sad to open a file without a close() statement
            ligand_file = open(args.ligand, 'rt', encoding="utf-8")
        except IOError:
            parser.error('Unable to find ligand file %s!' % args.ligand)

    if args.neutraln and (args.ff is None or args.ff.lower() != 'parse'):
        parser.error('--neutraln option only works with PARSE forcefield!')

    if args.neutralc and (args.ff is None or args.ff.lower() != 'parse'):
        parser.error('--neutralc option only works with PARSE forcefield!')


    path = Path(args.input_pdb)
    pdbFile = utilities.getPDBFile(args.input_pdb)

    args.isCIF = False
    if path.suffix.lower() == "cif":
        pdblist, errlist = cif.readCIF(pdbFile)
        args.isCIF = True
    else:
        pdblist, errlist = pdb.readPDB(pdbFile)

    if len(pdblist) == 0 and len(errlist) == 0:
        parser.error("Unable to find file %s!" % path)

    if len(errlist) != 0:
        if(isCIF):
            _LOGGER.warn("Warning: %s is a non-standard CIF file.\n", path)
        else:
            _LOGGER.warn("Warning: %s is a non-standard PDB file.\n", path)
        _LOGGER.error(errlist)

    args.outname = args.output_pqr

    # In case no extensions were specified or no extensions exist.
    # TODO - there are no command line options for extensions so I'm not sure what this does
    if not hasattr(args, 'active_extensions'):
        args.active_extensions = []
    elif args.active_extensions is None:
        args.active_extensions = []
    extensionOpts = args

    try:
        header, lines, missedligands = runPDB2PQR(pdblist, args)
    except PDB2PQRError as error:
        _LOGGER.error(error)
        raise PDB2PQRError(error)

    # Print the PQR file
    # TODO - move this to another function... this function is already way too long.
    outfile = open(args.output_pqr,"w")
    outfile.write(header)
    # Adding whitespaces if --whitespace is in the options
    for line in lines:
        if args.whitespace:
            if line[0:4] == 'ATOM':
                newline = line[0:6] + ' ' + line[6:16] + ' ' + line[16:38] + ' ' + line[38:46] + ' ' + line[46:]
                outfile.write(newline)
            elif line[0:6] == 'HETATM':
                newline = line[0:6] + ' ' + line[6:16] + ' ' + line[16:38] + ' ' + line[38:46] + ' ' + line[46:]
                outfile.write(newline)
            elif line[0:3] == "TER" and args.isCIF:
                pass
        else:
            if line[0:3] == "TER" and args.isCIF:
                pass
            else:
                outfile.write(line)
    if(args.isCIF):
        outfile.write("#\n")
    outfile.close()

    if args.apbs_input:
        from src import inputgen
        from src import psize
        method = "mg-auto"
        size = psize.Psize()
        size.parseInput(args.output_pqr)
        size.runPsize(args.output_pqr)
        #async = 0 # No async files here!
        input = inputgen.Input(args.output_pqr, size, method, 0, potdx=True)
        input.printInputFiles()
        input.dumpPickle()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    logging.captureWarnings(True)
    mainCommand()

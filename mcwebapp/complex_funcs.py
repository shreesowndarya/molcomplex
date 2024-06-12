from rdkit import Chem
from rdkit.Chem.Draw import rdDepictor
from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Chem.Draw import rdDepictor
import pandas as pd
import io
import base64
from itertools import combinations
import copy

#Canonicalize input smiles
def canonicalize_smiles(smiles):
    """ Return a consistent SMILES representation for the given molecule """
    mol = Chem.MolFromSmiles(smiles)
    return Chem.MolToSmiles(mol)

#### return a list of bonded atom ids & elements
def bonded_atoms(mol, single_only=False):
    bonded_list = []
    for bond in mol.GetBonds():
        m = bond.GetBeginAtom().GetIdx()
        m_atom = mol.GetAtomWithIdx(m).GetSymbol()
        
        n = bond.GetEndAtom().GetIdx()
        n_atom = mol.GetAtomWithIdx(n).GetSymbol()
        bt = bond.GetBondType()
        
        if single_only == False or bt == Chem.rdchem.BondType.SINGLE:
            bonded_list.append([m, n, m_atom, n_atom])
        
    return bonded_list


#### Fragment molecule at one bond position
def single_disconnect(mol, atom1, atom2):
    bond = mol.GetBondBetweenAtoms(atom1,atom2)
    bond_idx = bond.GetIdx()

    #break the bond
    mh = Chem.RWMol(mol)
    mh.RemoveBond(atom1, atom2)
    
    # Call SanitizeMol to update radicals
    try:
        Chem.SanitizeMol(mh)
    except Chem.rdchem.AtomKekulizeException:
        mh = Chem.RWMol(mol)
        Chem.Kekulize(mh,clearAromaticFlags=True)
        mh.RemoveBond(atom1, atom2)
        mh.GetAtomWithIdx(atom1).SetNoImplicit(True)
        mh.GetAtomWithIdx(atom2).SetNoImplicit(True)
        Chem.SanitizeMol(mh)
        Chem.rdmolops.SanitizeFlags.SANITIZE_NONE

    
    #add H to get rid of radicals
    radical_index = []
    for i, atom in enumerate(mh.GetAtoms()):
        if atom.GetNumRadicalElectrons() != 0:
            atom.SetNumExplicitHs(atom.GetNumImplicitHs() + 1)
            atom.SetNumRadicalElectrons(0)
    
    #Finish up
    newmol = mh.GetMol()
    
    return newmol,bond_idx

#### Fragment molecule at n bonds
def n_disconnect(mol, bond_list, n):
    newmols,bond_idx_list = [],[]
    bond_combinations = [list(comb) for comb in combinations(bond_list, n)]
        
    # bond = mol.GetBondBetweenAtoms(atom1,atom2)
    # bond_idx = bond.GetIdx()
    
    #make sure we dont have duplicate bonds, retain original bond numbering for visualization
    for i,combo in enumerate(bond_combinations):
        bond_check = []
        bonds_for_mol = []
        mh = Chem.RWMol(mol)
        for atom1,atom2,s1,s2 in combo:
            bond = mh.GetBondBetweenAtoms(atom1,atom2)
            bond_check.append(mol.GetBondBetweenAtoms(atom1,atom2).GetIdx())
            bonds_for_mol.append(bond.GetIdx())
        if len(list(set(bond_check))) != n:
               continue
                
        for atom1,atom2,s1,s2 in combo:
            bond = mh.GetBondBetweenAtoms(atom1,atom2)
            # Call SanitizeMol to update radicals
            try:
                temp_mol = copy.copy(mh)
                temp_mol.RemoveBond(atom1, atom2)
                Chem.SanitizeMol(temp_mol)
            except (Chem.rdchem.AtomKekulizeException,Chem.rdchem.KekulizeException):
                temp_mol = copy.copy(mh)
                try:
                    Chem.Kekulize(temp_mol,clearAromaticFlags=True)
                except:
                    pass
                temp_mol.RemoveBond(atom1, atom2)
                temp_mol.GetAtomWithIdx(atom1).SetNoImplicit(True)
                temp_mol.GetAtomWithIdx(atom2).SetNoImplicit(True)
                Chem.SanitizeMol(temp_mol)
                Chem.rdmolops.SanitizeFlags.SANITIZE_NONE

            #add H to get rid of radicals
            mh = temp_mol
            radical_index = []
            for i, atom in enumerate(mh.GetAtoms()):
                if atom.GetNumRadicalElectrons() != 0:
                    atom.SetNumExplicitHs(atom.GetNumImplicitHs() + 1)
                    atom.SetNumRadicalElectrons(0)
            # Chem.Kekulize(mh,clearAromaticFlags=True)
            # Chem.SanitizeMol(mh)
        
        #Finish up
        newmol = mh.GetMol()
        newmols.append(newmol)
        bond_idx_list.append(bonds_for_mol)

    return newmols, bond_idx_list


def parse_contents(smiles,n):
    mol = Chem.MolFromSmiles(smiles)
    bonds = bonded_atoms(mol, single_only=False)
    #### make a list of mol objects and smiles for unique retrosynthetic precursors
    precursor_mols = []
    precursor_smiles = []
    highlight_bonds = []
    highlight_atoms = []

    mols,bonds = n_disconnect(mol,bonds,n)

    for i,b in enumerate(bonds):
        if len(set(b)) == n:
            smi = Chem.MolToSmiles(mols[i])
            if smi not in precursor_smiles:
                precursor_smiles.append(smi)
                precursor_mols.append(mol)
                highlight_bonds.append(b)
   
    return precursor_mols, precursor_smiles, highlight_bonds, 


#display one mol
def smi2svg(smi,feature,feature_name):
    mol = Chem.MolFromSmiles(smi)
    rdDepictor.Compute2DCoords(mol)
    mc = Chem.Mol(mol.ToBinary())
    Chem.Kekulize(mc)
    legend = [f'Input Molecule\n{feature_name}: {feature:.3f}']
    #legend = ['']
    dopts = rdMolDraw2D.MolDrawOptions()
    #dopts.addBondIndices = True
    dopts.legendFontSize=20
    img = Chem.Draw.MolsToGridImage([mol], 
                                    molsPerRow=1, 
                                    subImgSize=(300,250),
                                    #subImgSize=(300,250),
                                    legends=legend,
                                    useSVG=True,
                                    drawOptions=dopts,
                                    )

    svg = img.replace('svg:','')
    
    return svg


#display multiple mols
def smis2svg(smiles,highlight_bonds,features,feature_name,sortby,mols_per_row):
    mols = [Chem.MolFromSmiles(smiles) for i in features]
    legend = []
    for i,mol in enumerate(mols): 
        rdDepictor.Compute2DCoords(mol)
        # mc = Chem.Mol(mol.ToBinary())
        # Chem.Kekulize(mc)
        legend.append(f'Fragment {i+1}\n{feature_name}: {features[i]:.3f}')

    # for i,bond in enumerate(highlight_bonds):
    #     mol = mols[i]
    #     mol.GetBondWithIdx(bond[0]).SetProp('bondNote',bond[0])


    #rdMolDraw2D.SetFontSize(32)
    dopts = rdMolDraw2D.MolDrawOptions()
    dopts.setHighlightColour((0.3,.8,.9))
    #dopts.addBondIndices = True
    dopts.legendFontSize=20
    img = Chem.Draw.MolsToGridImage(mols, 
                                    molsPerRow=mols_per_row, 
                                    highlightBondLists=highlight_bonds, 
                                    subImgSize=(300,300),
                                    legends=legend,
                                    drawOptions=dopts,
                                    useSVG=True,
                                    #maxMols=len(smiles)
                                    )

    svg = img.replace('svg:','')

    return svg

'''
Write excel
:parameter
    :param dtf: pandas table
:return
    link
'''
def download_file(df):
    xlsx_io = io.BytesIO()
    writer = pd.ExcelWriter(xlsx_io)
    df.to_excel(writer, index=False)
    writer._save() 
    xlsx_io.seek(0)
    media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    data = base64.b64encode(xlsx_io.read()).decode("utf-8")
    link = f'data:{media_type};base64,{data}'
    return link
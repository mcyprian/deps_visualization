import os
import re
import tempfile
import shutil
from abc import ABCMeta
from subprocess import CalledProcessError

from sclbuilder.graph import PackageGraph
from sclbuilder.recipe import Recipe
from sclbuilder.srpm_archive import SrpmArchive
from sclbuilder.utils import change_dir, subprocess_popen_call, edit_bootstrap
from sclbuilder.exceptions import MissingRecipeException

class Builder(metaclass=ABCMeta):
    '''
    Abstract superclass of builder classes.
    '''
    def __init__(self, rebuild_metadata):
        self.packages = set(rebuild_metadata.data['packages'])
        self.repo = rebuild_metadata.data['repo']
        self.rpm_dict = {}
        self.path = tempfile.mkdtemp()
        self.built_packages = set()
        self.built_rpms = set()
        self.graph = PackageGraph(self.repo, self.packages, self.rpm_dict)
        self.num_of_deps = {}
        self.circular_deps = []
        self.all_circular_deps  = set()
        try:
            self.recipes = rebuild_metadata.data['recipes']
        except IOError:
            print("Failed to load recipe {0}.".format(recipe))

    def __del__(self):
        shutil.rmtree(self.path)

    @property
    def path(self):
        return self.__path

    @path.setter
    def path(self, value):
        value += '/sclbuilder-{0}/'.format(self.repo) #TODO Use temp_dir instead?
        if not os.path.isdir(value):
            os.makedirs(value)
        self.__path = value

    @property
    def recipes(self):
        return self.__recipes

    @recipes.setter
    def recipes(self, recipe_files):
        if not recipe_files:
            self.__recipes = None
        else:
            self.__recipes = []
            for recipe in recipe_files:
                self.__recipes.append(Recipe(recipe))

    def get_relations(self):
        '''
        Runs graph analysis and get dependance tree and circular_deps
        '''
        self.graph.make_graph()
        (self.num_of_deps, self.circular_deps) = self.graph.analyse()
        if self.circular_deps and not self.recipes:
            raise MissingRecipeException("Missing recipes to resolve circular dependencies in graph.")
        for circle in self.circular_deps:
            self.all_circular_deps |= circle


    def build_ord_gen(self):
        '''
        Iterates over num_of_deps and build package that have all deps
        satisfied
        '''
        while self.packages > self.built_packages:
            for num in sorted(self.num_of_deps.keys()):
                if num == 0:
                    continue
                for package in self.num_of_deps[num]:
                    if package not in self.built_packages and self.deps_satisfied(package):
                        yield (package, False)

    def build_ord_recipe_gen(self):
        '''
        Iterates over num_of_deps, building circular_deps using recipes
        '''
        while self.packages > self.built_packages:
            for num in sorted(self.num_of_deps.keys()):
                if num == 0:
                    continue
                for pkg in self.num_of_deps[num]:
                    if pkg in self.built_packages:
                        continue
                    if pkg in self.all_circular_deps and\
                        self.recipe_deps_satisfied(self.find_recipe(pkg)): 
                        yield (pkg, True)
                    elif self.deps_satisfied(pkg):
                       yield (pkg, False)

    def deps_satisfied(self, package):
        '''
        Compares package deps with self.build_packages to
        check if are all dependancies already built
        '''
        if set(self.graph.G.successors(package)) <= self.built_packages:
            return True
        return False

    def recipe_deps_satisfied(self, recipe):
        '''
        Checks if all packages in recipe have satisfied their
        dependencies on packages that are not in recipe
        '''
        deps = set()
        for pkg in recipe.packages:
            deps |= set(self.graph.G.successors(pkg))

        if (deps - recipe.packages) <= self.built_packages:
            return True
        return False

    def build(self, package, verbose=True):
        self.built_packages.add(package)
        self.built_rpms |= set(self.rpm_dict[package])
        if verbose:
            print("Building {0}...".format(package))

    def run_building(self):
        '''
        First builds all packages without deps, then iterates over num_of_deps
        and simulate building of packages in right order
        '''
        if not self.num_of_deps:
            print("Nothing to build")
            return
        
        # Builds all packages without deps
        if 0 in self.num_of_deps.keys():
            for package in self.num_of_deps[0]:
                self.build(package)

        if self.recipes:
            build_ord_generator = self.build_ord_recipe_gen
        else:
            build_ord_generator = self.build_ord_gen

        for pkg, recipe in build_ord_generator():
            if recipe:
                self.build_following_recipe(self.find_recipe(pkg))
            else:
                self.build(pkg)

    def find_recipe(self, package):
        '''
        Search for recipe including package in self.recipes
        '''
        for recipe in self.recipes:
            if package in recipe.packages:
                return recipe
        raise MissingRecipeException("Recipe for package {0} not found".format(package))
    
    def build_following_recipe(self, recipe):
        '''
        Builds packages in order and macro values discribed in given
        recipe.
        '''
        for step in recipe.order:
            if len(step) == 1:
                print("Building package {0}".format(step[0]))
            else:
                print("Building package {0} {1}".format(step[0], step[1]))
                (macro, value) = step[1].split(' ')
                edit_bootstrap(self.pkg_files[step[0]].spec_file, macro, value)
                self.pkg_files[step[0]].pack()
            self.build(step[0], False)
    
    def get_files(self):
        '''
        Creates SrpmArchive object and downloads files for each package
        '''
        with change_dir(self.path):
            for package in self.packages:
                pkg_dir = self.path + package
                if not os.path.exists(pkg_dir):
                    os.mkdir(pkg_dir)
                self.pkg_files[package] = SrpmArchive(pkg_dir, package, self.repo)
                print("Getting files of {0}.".format(package))
                self.pkg_files[package].get(src=self.pkg_source)
    def make_rpm_dict(self):
        '''
        Makes dictionary of rpms created from srpm of each package.
        '''
        if not self.pkg_files:
            self.get_files()
        for package in self.packages:
            self.rpm_dict[package] = self.get_rpms(self.pkg_files[package].spec_file)

    def get_rpms(self, spec_file):
        '''
        Returns list of rpms created from spec_file
        '''
        rpm_pattern = re.compile("(^.*)-\d+.\d+.\d+.*$")
        # TODO improve to search
        # python3-docutils-0.12-0.5.20140510svn7747.fc22.noarch
        proc_data = subprocess_popen_call(["rpm", "-q", "--specfile", "--define",
                                      "scl_prefix " + self.prefix, spec_file])
        if proc_data['returncode']:
            print(proc_data['stderr'])
            raise CalledProcessError(cmd='rpm', returncode=proc_data['returncode'])
    #TODO stderr to log
        rpms =  proc_data['stdout'].splitlines()
        return [rpm_pattern.search(x).groups()[0] for x in rpms]


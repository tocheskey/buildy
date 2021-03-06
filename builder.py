import os
import shlex
import shutil
import tarfile
import datetime
import debian.changelog
import subprocess

class BuildyBuilder:

    def __init__(self, builder_name, project, config, orig, vcs_obj):
        self.builder_name = builder_name
        self.project = project
        self.config = config

        self.name = self.config.get(project, 'name')
        self.version = self.config.get(project, 'version')
        self.orig = orig
        self.template = self.config.get(project, 'package-template')
        self.work_dir = self.config.get(project, 'work-dir')
        self.path = os.path.join(self.work_dir, 'build')
        self.vcs_obj = vcs_obj
        self.buildresult = self.config.get(self.builder_name, 'output-dir')
        self.buildbase = self.config.get(self.builder_name, 'buildbase')


    def build(self):
        raise NotImplementedError, "This method should be overridden!"

    def create_build_env(self):
        revision = self.vcs_obj.get_revision()
        environment = dict(os.environ)
        buildy_environment = dict(
            BUILDY_PROJECT_NAME=str(self.name),
            BUILDY_PROJECT_VERSION=str(self.version),
            BUILDY_PROJECT_REVISION=str(revision))
        environment.update(buildy_environment)
        return environment

class BuildyDebian(BuildyBuilder):

    def __init__(self, builder_name, project, config, orig, vcs_obj):
        BuildyBuilder.__init__(self, builder_name, project, config, orig, vcs_obj)
        self.changelog_distribution = self.config.get(self.builder_name, 'changelog-distribution')
        self.changelog_urgency = self.config.get(self.builder_name, 'changelog-urgency')
        self.changelog_author = self.config.get(self.builder_name, 'changelog-author')
        self.changelog_entry = self.config.get(self.builder_name, 'changelog-entry')
        if self.config.has_option(self.builder_name, 'builder-command'):
            self.builderbinary = self.config.get(self.builder_name, 'builder-command').split()
        else:
            self.builderbinary = []
        if self.config.has_option(self.builder_name, 'builder-arguments'):
            builderarguments = self.config.get(self.builder_name, 'builder-arguments')
            self.builderarguments = shlex.split(builderarguments)
        else:
            self.builderarguments = []
        self.buildfile = None
        self.builderoptions = None

    def prepare(self):
        # unpack tarball
        os.chdir(self.path)
        tar = tarfile.open(self.orig)
        tar.extractall()
        tar.close()
        # copy orig.tar.gz under the correct name to the build place
        final_orig = '%s_%s+%s.orig.tar' % (self.vcs_obj.get_name(), self.vcs_obj.get_version(), self.vcs_obj.get_fancy_revision())
        if self.orig.endswith('bz2'):
            final_orig += '.bz2'
        elif self.orig.endswith('gz'):
            final_orig += '.gz'
        else:
            raise NotImplementedError, "Only .gz and .bz2 tarballs are supported!"
        shutil.copy2(self.orig, os.path.join(self.path, final_orig))
        # copy the packaging template to the exctracted tarball
        shutil.copytree(self.template, os.path.join(self.vcs_obj.get_useful_filename(), 'debian'))
        os.chdir(self.vcs_obj.get_useful_filename())
        # add new changelog entry
        cf = open('./debian/changelog', "r")
        changelog = debian.changelog.Changelog(cf)
        #print changelog.get_package()
        new_version = '%s+%s-1' % (self.vcs_obj.get_version(), self.vcs_obj.get_fancy_revision())
        # FIXME! Why is %z empty???
        date = datetime.datetime.strftime(datetime.datetime.now(), "%a, %d %b %Y %H:%M:%S +0000")
        changelog.new_block(package=self.name, version=new_version, distributions=self.changelog_distribution, urgency=self.changelog_urgency, author=self.changelog_author, date=date)
        changelog.add_change('')
        changelog.add_change('  * %s' % self.changelog_entry)
        changelog.add_change('')
        cf_new = open('./debian/changelog', "w")
        changelog.write_to_open_file(cf_new)
        cf_new.close()
        cf.close()
        # build a source package
        #print os.path.abspath('.')
        buildy_env = self.create_build_env()
        retcode = subprocess.call(["dpkg-buildpackage", "-us", "-uc", "-S"], env=buildy_env)
        self.buildfile = os.path.join(self.path, '%s_%s.dsc' % (self.name, new_version))
        return retcode

    def build(self):
        if not self.builderbinary:
            raise NotImplementedError, "I don't know which builder to call."
        if not self.buildfile:
            raise IOError, "What should I build?"
        buildy_env = self.create_build_env()
        command = self.builderbinary + self.builderoptions + self.builderarguments + [self.buildfile]
        retcode = subprocess.call(command, env=buildy_env)
        return retcode

class BuildyDebianPbuilder(BuildyDebian):

    def __init__(self, builder_name, project, c, orig, vcs_obj):
        BuildyDebian.__init__(self, builder_name, project, c, orig, vcs_obj)
        if not self.builderbinary:
            self.builderbinary = ['pbuilder']
        self.builderoptions = ['--build', '--basetgz', self.buildbase, '--buildresult', self.buildresult]

class BuildyDebianCowBuilder(BuildyDebianPbuilder):

    def __init__(self, builder_name, project, c, orig, vcs_obj):
        BuildyDebian.__init__(self, builder_name, project, c, orig, vcs_obj)
        if not self.builderbinary:
            self.builderbinary = ['cowbuilder']
        self.builderoptions = ['--build', '--basepath', self.buildbase, '--buildresult', self.buildresult]

